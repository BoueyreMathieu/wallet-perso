"""Lecture des exports CSV du Crédit Agricole (« Télécharger mes opérations »).

Format observé :
- encodage Windows-1252, séparateur « ; » ;
- un en-tête libre (date de téléchargement, titulaire, compte, solde) ;
- puis « Date d'opération;Libellé;Débit euros;Crédit euros; » ;
- le libellé tient sur 6 lignes : type d'opération, détail, complément,
  référence de mandat, identifiant créancier (ICS), référence ;
- montants au format « 2 025,82 ».

Ce module n'utilise que la bibliothèque standard : il peut tourner sans base de données.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.connectors.base import RawTransaction, Statement

HEADER_START = "Date d'opération;"

CARD_RE = re.compile(r"^X\d{4}\s+(?P<raw>.*?)\s+(?P<day>\d{2}/\d{2})(?:\s+-\s+(?P<name>.*))?$")
ACCOUNT_RE = re.compile(r"^(?P<label>.+?)\s+carte n°\s*(?P<number>\d+)", re.IGNORECASE)
BALANCE_RE = re.compile(r"Solde au (?P<date>\d{2}/\d{2}/\d{4})\s+(?P<amount>-?[\d\s  .,]+)\s*€")
HOLDER_RE = re.compile(r"^(MONSIEUR|MADAME|MADEMOISELLE|M\.|MME|MLLE|MR|M OU MME)\s+\S+", re.IGNORECASE)
PAYMENT_PREFIX_RE = re.compile(r"^(PAYPAL_?\*|SUMUP\s*\*|ZETTLE_?\*|SQ\s*\*)\s*", re.IGNORECASE)
TRANSFER_PREFIX_RE = re.compile(
    r"^(VIR(EMENT)?\s+INST(ANTANE)?\s+(WERO\s+)?(VERS|DE)\s+|WERO\s+(VERS|DE)\s+|WEB\s+|DE\s+)", re.IGNORECASE
)


SMALL_WORDS = {"de", "du", "des", "la", "le", "les", "et", "au", "aux", "en", "sur", "sous"}


class CAParseError(ValueError):
    pass


@dataclass
class ParsedTransaction:
    booked_at: date
    amount_cents: int
    op_type: str
    detail: str
    raw_label: str
    creditor_id: str | None = None
    card_raw: str | None = None  # préfixe brut du commerçant pour un paiement carte
    merchant_hint: str | None = None
    dedup_hash: str = ""


@dataclass
class ParsedStatement:
    account_label: str | None
    account_number: str | None
    holder: str | None
    balance_date: date | None
    balance_cents: int | None
    transactions: list[ParsedTransaction] = field(default_factory=list)

    @property
    def period(self) -> tuple[date, date] | None:
        if not self.transactions:
            return None
        days = [t.booked_at for t in self.transactions]
        return min(days), max(days)


# --- Utilitaires -----------------------------------------------------------


def decode(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def parse_amount(text: str) -> int | None:
    """« 2 025,82 » → 202582 centimes. Chaîne vide → None."""
    clean = re.sub(r"[\s  €]", "", text or "")
    if not clean:
        return None
    clean = clean.replace(".", "").replace(",", ".") if "," in clean else clean
    try:
        return int((Decimal(clean) * 100).quantize(Decimal("1")))
    except InvalidOperation as e:
        raise CAParseError(f"Montant illisible : {text!r}") from e


def parse_date(text: str) -> date:
    return datetime.strptime(text.strip(), "%d/%m/%Y").date()


def smart_title(text: str) -> str:
    """Met en forme un nom tout en majuscules ; laisse tel quel un nom déjà mis en forme."""
    text = re.sub(r"\s+", " ", text).strip(" -*")
    if not (text.isupper() or text.islower()):
        return text
    words = []
    for i, w in enumerate(text.split(" ")):
        lw = w.lower()
        if lw in SMALL_WORDS:
            words.append(lw if i > 0 else w.capitalize())
        elif len(w) <= 2 and w.isalpha():
            words.append(w.upper())  # sigle probable : « OL », « IT »
        else:
            words.append(w.capitalize())
    return " ".join(words)


def _clean_payee(text: str) -> str:
    text = PAYMENT_PREFIX_RE.sub("", text.strip())
    text = TRANSFER_PREFIX_RE.sub("", text)
    # Retire les numéros / références en fin de chaîne : « ACME CORP 123456 » → « ACME CORP ».
    text = re.sub(r"(\s+[A-Z0-9]*\d[A-Z0-9/]*)+$", "", text)
    return smart_title(text) if text else ""


# --- Marchands ---------------------------------------------------------------


def _merchant_hint(op_type: str, detail: str) -> str | None:
    t = op_type.lower()
    segs = [s.strip() for s in detail.split(" - ") if s.strip()]
    if not segs:
        return None
    if "paypal" in detail.lower() and t.startswith("prélèvement"):
        return "PayPal"
    if t.startswith("paiement par carte"):
        m = CARD_RE.match(detail)
        if m:
            return m.group("name").strip() if m.group("name") else smart_title(PAYMENT_PREFIX_RE.sub("", m.group("raw")))
        return smart_title(detail)
    if t.startswith("prélèvement"):
        if len(segs) >= 3:
            return segs[1]
        if len(segs) == 2 and len(segs[1]) <= 30 and not re.search(r"\d", segs[1]):
            return segs[1]
        return smart_title(segs[0])
    if t.startswith("virement"):
        name = _clean_payee(segs[0])
        return name or None
    if t.startswith(("cotisation", "frais", "régul")):
        return "Crédit Agricole"
    return None


def resolve_merchants(transactions: list[ParsedTransaction], known_aliases: dict[str, str] | None = None) -> dict[str, str]:
    """Harmonise les noms de marchands.

    Le Crédit Agricole n'ajoute le nom « propre » (« … - Nom du commerce ») que sur une partie
    des paiements carte. On retient donc l'association préfixe brut → nom propre, ainsi que
    identifiant créancier (ICS) → nom, et on l'applique aux lignes qui n'en ont pas.
    Renvoie les alias appris (clé → nom) pour les mémoriser en base.
    """
    aliases: dict[str, str] = dict(known_aliases or {})
    learned: dict[str, str] = {}
    # 1er passage : apprendre depuis les lignes enrichies.
    for t in transactions:
        if t.card_raw and CARD_RE.match(t.detail) and CARD_RE.match(t.detail).group("name"):
            key = f"carte:{t.card_raw.upper()}"
            if key not in aliases:
                aliases[key] = learned[key] = t.merchant_hint or ""
        if t.creditor_id and t.merchant_hint and t.detail.count(" - ") >= 2:
            key = f"ics:{t.creditor_id}"
            if key not in aliases:
                aliases[key] = learned[key] = t.merchant_hint
    # 2e passage : appliquer.
    for t in transactions:
        if t.card_raw and f"carte:{t.card_raw.upper()}" in aliases:
            t.merchant_hint = aliases[f"carte:{t.card_raw.upper()}"] or t.merchant_hint
        elif t.creditor_id and f"ics:{t.creditor_id}" in aliases:
            t.merchant_hint = aliases[f"ics:{t.creditor_id}"]
    return learned


# --- Lecture du fichier ------------------------------------------------------


def _parse_header(lines: list[str]) -> tuple[str | None, str | None, str | None, date | None, int | None]:
    label = number = holder = None
    bal_date = bal = None
    for line in lines:
        line = line.strip().rstrip(";").strip()
        if not line:
            continue
        if m := ACCOUNT_RE.match(line):
            label, number = m.group("label").strip(), m.group("number")
        elif m := BALANCE_RE.search(line):
            bal_date, bal = parse_date(m.group("date")), parse_amount(m.group("amount"))
        elif holder is None and HOLDER_RE.match(line):
            holder = re.sub(r"\s+", " ", line)
    return label, number, holder, bal_date, bal


def dedup_hash(booked_at: date, amount_cents: int, raw_label: str, occurrence: int) -> str:
    label = re.sub(r"\s+", " ", raw_label).strip().upper()
    key = f"{booked_at.isoformat()}|{amount_cents}|{label}|{occurrence}"
    return hashlib.sha256(key.encode()).hexdigest()


def parse(raw: bytes) -> ParsedStatement:
    text = decode(raw)
    start = text.find(HEADER_START)
    if start < 0:
        raise CAParseError("Ce fichier ne ressemble pas à un export CSV du Crédit Agricole (en-tête introuvable).")

    label, number, holder, bal_date, bal = _parse_header(text[:start].splitlines())
    reader = csv.reader(io.StringIO(text[start:]), delimiter=";")
    next(reader)  # en-tête des colonnes

    stmt = ParsedStatement(label, number, holder, bal_date, bal)
    seen: Counter[tuple] = Counter()
    for i, row in enumerate(reader, start=2):
        if not row or not row[0].strip():
            continue
        if len(row) < 4:
            raise CAParseError(f"Ligne {i} incomplète : {row!r}")
        parts = [p.strip() for p in row[1].split("\n")]
        parts += [""] * (6 - len(parts))
        op_type, detail = parts[0], parts[1]
        debit, credit = parse_amount(row[2]), parse_amount(row[3])
        if debit is None and credit is None:
            raise CAParseError(f"Ligne {i} sans montant.")
        amount = (credit or 0) - (debit or 0)
        booked = parse_date(row[0])
        raw_label = " | ".join(p for p in parts if p)

        card = CARD_RE.match(detail) if op_type.lower().startswith("paiement par carte") else None
        t = ParsedTransaction(
            booked_at=booked,
            amount_cents=amount,
            op_type=op_type,
            detail=detail,
            raw_label=raw_label,
            creditor_id=parts[4] or None,
            card_raw=card.group("raw").strip() if card else None,
            merchant_hint=_merchant_hint(op_type, detail),
        )
        # Deux opérations identiques le même jour sont possibles (deux cafés…) : on les numérote.
        key = (booked, amount, raw_label)
        t.dedup_hash = dedup_hash(booked, amount, raw_label, seen[key])
        seen[key] += 1
        stmt.transactions.append(t)

    if not stmt.transactions:
        raise CAParseError("Aucune opération trouvée dans le fichier.")
    return stmt


def to_statement(raw: bytes, known_aliases: dict[str, str] | None = None) -> Statement:
    """Lit un export CA et le convertit au format commun des connecteurs."""
    st = parse(raw)
    learned = resolve_merchants(st.transactions, known_aliases)
    return Statement(
        source="csv_credit_agricole",
        account_external_id=st.account_number,
        account_label=st.account_label,
        holder=st.holder,
        balance_date=st.balance_date,
        balance_cents=st.balance_cents,
        transactions=[
            RawTransaction(
                booked_at=t.booked_at,
                amount_cents=t.amount_cents,
                raw_label=t.raw_label,
                dedup_key=t.dedup_hash,
                merchant_hint=t.merchant_hint,
            )
            for t in st.transactions
        ],
        merchant_aliases=learned,
    )
