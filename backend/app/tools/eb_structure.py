"""Décrit la STRUCTURE des opérations reçues d'Enable Banking, sans en révéler le contenu.

Sortie en Markdown, à copier-coller à Claude (même principe que scripts/csv_structure.py) :
  - pour chaque champ JSON : taux de présence, type, « formes » masquées (lettres → A/a, chiffres → 9) ;
  - les valeurs réelles ne sont affichées QUE pour les champs de code/statut (liste REVEAL ci-dessous)
    et ceux que tu ajoutes avec --show ;
  - pour un compte PayPal : des COMPTEURS de correspondances avec les prélèvements PayPal des autres
    comptes (même montant, dates proches), sans aucun montant ni libellé.

Usage (depuis le dossier wallet-perso) :
  docker compose exec api python -m app.tools.eb_structure                 # liste les comptes synchronisés
  docker compose exec api python -m app.tools.eb_structure --account 2     # structure du compte n° 2
  docker compose exec api python -m app.tools.eb_structure --account 2 --days 180 --show bank_transaction_code.description
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from app.db import get_sessionmaker
from app.models import Account, Connection, Transaction
from app.services import sync

REVEAL = {
    "status",
    "credit_debit_indicator",
    "transaction_amount.currency",
    "bank_transaction_code.code",
    "bank_transaction_code.sub_code",
    "balance_after_transaction.currency",
}
SAMPLE_SHAPES = 4


def shape(value: str, limit: int = 50) -> str:
    out = re.sub(r"[^\W\d_]+", lambda m: "A" if m.group(0)[0].isupper() else "a", value)
    out = re.sub(r"\d", "9", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out if len(out) <= limit else out[: limit - 1] + "…"


def walk(value, path: str, out: list[tuple[str, object]]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            walk(v, f"{path}.{k}" if path else k, out)
    elif isinstance(value, list):
        out.append((f"{path}#len", len(value)))
        for v in value:
            walk(v, f"{path}[]", out)
    else:
        out.append((path, value))


def accounts_list(db) -> list[tuple[Connection, dict]]:
    rows = []
    for c in db.scalars(select(Connection).where(Connection.provider == sync.PROVIDER).order_by(Connection.id)):
        for a in sync._secrets(c).get("accounts", []):
            rows.append((c, a))
    return rows


def describe(txs: list[dict], reveal: set[str]) -> list[str]:
    present: Counter = Counter()
    types: dict[str, Counter] = defaultdict(Counter)
    shapes: dict[str, Counter] = defaultdict(Counter)
    values: dict[str, Counter] = defaultdict(Counter)
    for t in txs:
        flat: list[tuple[str, object]] = []
        walk(t, "", flat)
        seen = set()
        for path, v in flat:
            if v is None or v == "":
                continue
            if path not in seen:
                present[path] += 1
                seen.add(path)
            types[path][type(v).__name__] += 1
            if path.endswith("#len"):
                values[path][v] += 1
            elif path in reveal:
                values[path][str(v)] += 1
            else:
                shapes[path][shape(str(v))] += 1
    n = len(txs) or 1
    lines = ["| Champ | Présent | Type | Valeurs / formes |", "|---|---|---|---|"]
    for path in sorted(present):
        if path in values:
            detail = ", ".join(f"`{k}` ×{c}" for k, c in values[path].most_common(12))
        else:
            detail = ", ".join(f"`{k}` ×{c}" for k, c in shapes[path].most_common(SAMPLE_SHAPES))
        typ = "/".join(types[path])
        lines.append(f"| `{path}` | {present[path] * 100 // n} % | {typ} | {detail} |")
    return lines


def paypal_matches(db, account_id: int, txs: list[dict]) -> list[str]:
    """Compteurs : opérations de ce compte qui ont un « jumeau » (même montant opposé, ±7 jours)
    parmi les opérations « PayPal » des autres comptes. Aucun montant ni libellé affiché."""
    from app.connectors.enable_banking import _cents

    others = [
        t
        for t in db.scalars(select(Transaction).join(Account, Transaction.account_id == Account.id).where(Account.id != account_id))
        if t.amount_cents < 0 and "paypal" in ((t.raw_label or "") + " " + (t.merchant.name if t.merchant else "")).lower()
    ]
    by_amount: dict[int, list[date]] = defaultdict(list)
    for t in others:
        by_amount[-t.amount_cents].append(t.booked_at)
    stats: Counter = Counter()
    for t in txs:
        amount = _cents((t.get("transaction_amount") or {}).get("amount", "0"))
        sign = (t.get("credit_debit_indicator") or "?").upper()
        day = str(t.get("booking_date") or t.get("value_date") or t.get("transaction_date"))[:10]
        try:
            d = date.fromisoformat(day)
        except ValueError:
            continue
        twin = any(abs((d - od).days) <= 7 for od in by_amount.get(abs(amount), []))
        stats[(sign, twin)] += 1
    out = ["", "### Correspondances avec les prélèvements « PayPal » des autres comptes (compteurs seulement)", ""]
    out.append(f"Prélèvements PayPal trouvés sur les autres comptes : {len(others)}")
    for (sign, twin), c in sorted(stats.items()):
        out.append(f"- {sign} {'avec' if twin else 'sans'} jumeau bancaire (même montant, ±7 j) : {c}")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--account", type=int, help="numéro du compte (voir la liste sans option)")
    p.add_argument("--days", type=int, default=60, help="historique analysé (jours, défaut 60 ; beaucoup de banques limitent à 90)")
    p.add_argument("--pending", action="store_true", help="demander explicitement les opérations à venir (transaction_status=PDNG)")
    p.add_argument("--show", nargs="*", default=[], help="champs dont afficher les valeurs réelles (codes/statuts uniquement)")
    args = p.parse_args()

    with get_sessionmaker()() as db:
        rows = accounts_list(db)
        if not args.account:
            print("Comptes synchronisés (relance avec --account N) :")
            for i, (c, a) in enumerate(rows, 1):
                acc = db.get(Account, a["account_id"]) if a.get("account_id") else None
                print(f"  {i}. {c.label} → {acc.name + ' (' + acc.type + ')' if acc else 'non associé'}")
            return
        c, a = rows[args.account - 1]
        acc = db.get(Account, a["account_id"]) if a.get("account_id") else None
        txs = sync.get_client().transactions(a["uid"], date.today() - timedelta(days=args.days), "PDNG" if args.pending else None)
        print(f"## {c.label} — compte n° {args.account} ({acc.type if acc else 'non associé'}) — {len(txs)} opérations sur {args.days} jours\n")
        print("\n".join(describe(txs, REVEAL | set(args.show))))
        if acc is not None and (acc.type == "paypal" or "paypal" in c.label.lower()):
            print("\n".join(paypal_matches(db, acc.id, txs)))


if __name__ == "__main__":
    main()
