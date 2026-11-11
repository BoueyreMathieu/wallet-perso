"""Lecture de l'export CSV de l'activité PayPal (paypal.com → Activité → Télécharger, format CSV).

Ce qui est importé :
- les achats (« Paiement préapprouvé… », « Paiement Express Checkout »…), avec vendeur et objet ;
- les approvisionnements depuis la banque (« Virement bancaire sur le compte PayPal ») : ils servent
  au rapprochement avec le compte bancaire et sont exclus des statistiques ;
- les autres mouvements réels (argent reçu, remboursements…).
Ce qui est ignoré :
- les lignes « Mémo » (autorisations, annulations d'autorisation : aucun mouvement d'argent),
- les suspensions de compte et leur annulation (réservations temporaires qui s'annulent),
- les opérations annulées.
Jamais lus ni stockés : adresses, téléphones, e-mails (seule une empreinte de l'e-mail du titulaire
sert à reconnaître le compte).

Pur Python, sans base de données.
"""

from __future__ import annotations

import csv
import hashlib
import io
import unicodedata
from collections import Counter
from datetime import datetime

from app.connectors.base import RawTransaction, Statement, stable_hash
from app.importers.credit_agricole import decode, parse_amount

FUNDING_PATH = "Transferts/PayPal"
REQUIRED = ["Date", "Type", "État", "Net", "Numéro de transaction", "Impact sur le solde"]


class PayPalParseError(ValueError):
    pass


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower().strip()


def role_of(op_type: str, impact: str) -> str | None:
    """Rôle d'une ligne : « achat », « approvisionnement », « autre », ou None si à ignorer."""
    t, i = _norm(op_type), _norm(impact)
    if i == "memo":
        return None
    if "suspension" in t:
        return None
    if "virement bancaire sur le compte paypal" in t or "approvisionnement" in t:
        return "approvisionnement"
    if i == "debit":
        return "achat"
    return "autre"


def parse(raw: bytes) -> Statement:
    text = decode(raw)
    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames or []
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        raise PayPalParseError(
            "Ce fichier ne ressemble pas à un export d'activité PayPal (colonnes manquantes : " + ", ".join(missing) + ")."
        )

    txs: list[RawTransaction] = []
    last: tuple[datetime, int] | None = None
    own_emails: Counter[str] = Counter()
    for i, row in enumerate(reader, start=2):
        role = role_of(row.get("Type", ""), row.get("Impact sur le solde", ""))
        if role is None or _norm(row.get("État", "")) == "annule":
            continue
        txid = (row.get("Numéro de transaction") or "").strip()
        if not txid:
            raise PayPalParseError(f"Ligne {i} sans numéro de transaction.")
        amount = parse_amount(row.get("Net", ""))
        if amount is None:
            raise PayPalParseError(f"Ligne {i} sans montant.")
        try:
            day = datetime.strptime(row["Date"].strip(), "%d/%m/%Y")
        except ValueError as e:
            raise PayPalParseError(f"Ligne {i} : date illisible.") from e
        try:
            moment = datetime.strptime(f"{row['Date'].strip()} {(row.get('Heure') or '00:00:00').strip()}", "%d/%m/%Y %H:%M:%S")
        except ValueError:
            moment = day

        op_type = (row.get("Type") or "").strip()
        vendor = (row.get("Nom") or "").strip() or None
        item = (row.get("Objet") or row.get("Titre de l'objet") or "").strip() or None
        ref = (row.get("Numéro de la transaction de référence") or "").strip() or None
        details = {"source": "PayPal", "role": role, "type": op_type, "transaction": txid}
        if vendor:
            details["vendeur"] = vendor
        if item:
            details["objet"] = item
        if ref:
            details["reference"] = ref

        if role == "achat" and row.get("De l'adresse email"):
            own_emails[row["De l'adresse email"].strip().lower()] += 1

        funding = role == "approvisionnement"
        txs.append(
            RawTransaction(
                booked_at=day.date(),
                amount_cents=amount,
                raw_label=" | ".join(p for p in (op_type, vendor, item) if p),
                dedup_key=stable_hash("paypal", txid),
                merchant_hint=None if funding else vendor,
                external_id=txid,
                status=_norm(row.get("État", "")) or None,
                details=details,
                counted=not funding,
                force_category_path=FUNDING_PATH if funding else None,
            )
        )
        balance = parse_amount(row.get("Solde", ""))
        if balance is not None and (last is None or moment >= last[0]):
            last = (moment, balance)

    if not txs:
        raise PayPalParseError("Aucune opération exploitable dans le fichier.")
    account_id = None
    if own_emails:
        email = own_emails.most_common(1)[0][0]
        account_id = "paypal:" + hashlib.sha256(email.encode()).hexdigest()[:16]
    return Statement(
        source="csv_paypal",
        account_external_id=account_id,
        account_label="PayPal",
        balance_date=last[0].date() if last else None,
        balance_cents=last[1] if last else None,
        transactions=txs,
    )
