"""Rapprochement entre le compte bancaire et PayPal.

Quand PayPal se fait payer par la banque, on retrouve trois lignes :
  banque  : prélèvement « PayPal »          −X  (date J)
  PayPal  : « Virement bancaire sur le compte PayPal » +X (date J-quelques jours), dont la
            référence pointe vers…
  PayPal  : l'achat réel chez le vendeur      −X
Après rapprochement :
  - la ligne bancaire devient la vraie dépense : vendeur, catégorie et infos de l'achat ;
  - l'achat PayPal reste visible mais n'est plus compté (sinon double comptage) ;
  - l'approvisionnement est un transfert, non compté.
Avec la synchro Enable Banking, PayPal ne fournit que les achats (pas les approvisionnements) :
le prélèvement bancaire −X est alors rapproché directement de l'achat PayPal −X (dates proches).
En cas de doute (plusieurs candidats aussi proches), on ne devine pas : rien n'est rapproché.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Account, Transaction
from app.services.categorizing import Categorizer

DAYS_BEFORE = 7  # l'approvisionnement PayPal peut précéder le prélèvement bancaire de quelques jours
DAYS_AFTER = 2
LINK_KEYS = ("via", "vendeur", "objet", "paypal_transaction", "match_text", "orig_merchant_id")


def _is_paypal_debit(t: Transaction) -> bool:
    if t.amount_cents >= 0 or (t.details or {}).get("no_link"):
        return False
    name = (t.merchant.name if t.merchant else "") or ""
    return name.lower() == "paypal" or "paypal" in t.raw_label.lower()


def link(bank: Transaction, funding: Transaction | None, purchase: Transaction | None) -> None:
    if funding is not None:
        bank.transfer_pair_id, funding.transfer_pair_id = funding.id, bank.id
    info = {"via": "PayPal"}
    if purchase is not None:
        bank.linked_id, purchase.linked_id = purchase.id, bank.id
        pd = purchase.details or {}
        info.update(
            {
                "vendeur": pd.get("vendeur") or (purchase.merchant.name if purchase.merchant else None),
                "objet": pd.get("objet"),
                "paypal_transaction": pd.get("transaction"),
                "match_text": purchase.raw_label,
                "orig_merchant_id": bank.merchant_id,
            }
        )
        if purchase.merchant is not None:
            bank.merchant = purchase.merchant
        purchase.counted = False
    bank.details = {**(bank.details or {}), **{k: v for k, v in info.items() if v is not None}}


def sync_category(src: Transaction, dst: Transaction) -> None:
    dst.category_id, dst.is_transfer, dst.category_locked = src.category_id, src.is_transfer, src.category_locked


def reconcile_paypal(db: Session) -> int:
    """Rapproche les prélèvements PayPal bancaires non encore liés. Renvoie le nombre de rapprochements."""
    load = select(Transaction).options(selectinload(Transaction.merchant)).join(Account, Transaction.account_id == Account.id)
    paypal_rows = db.scalars(load.where(Account.type == "paypal")).all()
    fundings = [
        t for t in paypal_rows
        if (t.details or {}).get("role") == "approvisionnement" and t.transfer_pair_id is None
    ]
    # Achats venant de la synchro (sans rôle) : rapprochement direct avec le prélèvement bancaire.
    direct = [
        t for t in paypal_rows
        if t.amount_cents < 0 and not (t.details or {}).get("role") and t.linked_id is None and not (t.details or {}).get("no_link")
    ]
    if not fundings and not direct:
        return 0
    purchases = {(t.details or {}).get("transaction"): t for t in paypal_rows if (t.details or {}).get("role") == "achat"}
    bank_rows = [
        t for t in db.scalars(load.where(Account.type != "paypal", Transaction.transfer_pair_id.is_(None)))
        if _is_paypal_debit(t) and t.linked_id is None
    ]

    # Candidats : même montant (signes opposés), approvisionnement dans la fenêtre de dates.
    options: dict[int, list[tuple[int, Transaction]]] = {}
    for b in bank_rows:
        lo, hi = b.booked_at - timedelta(days=DAYS_BEFORE), b.booked_at + timedelta(days=DAYS_AFTER)
        cands = [(abs((b.booked_at - f.booked_at).days), f) for f in fundings if f.amount_cents == -b.amount_cents and lo <= f.booked_at <= hi]
        if cands:
            options[b.id] = sorted(cands, key=lambda c: (c[0], c[1].id))

    by_id = {b.id: b for b in bank_rows}
    taken: set[int] = set()
    linked: list[Transaction] = []
    # Les cas les plus nets d'abord (écart de dates le plus faible).
    for bid in sorted(options, key=lambda i: options[i][0][0]):
        free = [(d, f) for d, f in options[bid] if f.id not in taken]
        if not free:
            continue
        if len(free) > 1 and free[0][0] == free[1][0]:
            continue  # ambigu : deux approvisionnements aussi proches → on ne devine pas
        funding = free[0][1]
        purchase = purchases.get((funding.details or {}).get("reference"))
        if purchase is not None and purchase.linked_id is not None:
            purchase = None
        link(by_id[bid], funding, purchase)
        taken.add(funding.id)
        linked.append(by_id[bid])
        if purchase is not None:
            linked.append(purchase)

    # 2e passe : prélèvements restants ↔ achats PayPal synchronisés (même montant, dates proches).
    done = {t.id for t in linked}
    rest = [b for b in bank_rows if b.id not in done]
    direct_options: dict[int, list[tuple[int, Transaction]]] = {}
    for b in rest:
        lo, hi = b.booked_at - timedelta(days=DAYS_BEFORE), b.booked_at + timedelta(days=DAYS_AFTER)
        cands = [(abs((b.booked_at - p.booked_at).days), p) for p in direct if p.amount_cents == b.amount_cents and lo <= p.booked_at <= hi]
        if cands:
            direct_options[b.id] = sorted(cands, key=lambda c: (c[0], c[1].id))
    used: set[int] = set()
    for bid in sorted(direct_options, key=lambda i: (direct_options[i][0][0], i)):
        free = [(d, p) for d, p in direct_options[bid] if p.id not in used]
        if not free or (len(free) > 1 and free[0][0] == free[1][0]):
            continue
        purchase = free[0][1]
        link(by_id[bid], None, purchase)
        used.add(purchase.id)
        linked.extend([by_id[bid], purchase])

    if linked:
        db.flush()
        Categorizer(db).apply(linked)
        for t in linked:
            other = next((x for x in linked if x.id == t.linked_id), None)
            if other is not None and t.category_locked and not other.category_locked:
                sync_category(t, other)  # une catégorie choisie à la main l'emporte
    return sum(1 for t in linked if t.account.type != "paypal")


def unlink(db: Session, t: Transaction) -> None:
    """Défait un rapprochement (depuis la ligne bancaire ou la ligne PayPal)."""
    on_paypal = t.account.type == "paypal"
    if not on_paypal:
        bank = t
    else:
        twin_id = t.linked_id or t.transfer_pair_id  # depuis l'achat ou depuis l'approvisionnement
        bank = db.get(Transaction, twin_id) if twin_id else None
    if bank is not None and bank.linked_id:
        purchase = db.get(Transaction, bank.linked_id)
    else:
        purchase = t if on_paypal and (t.details or {}).get("role") == "achat" else None
    if bank is None:
        if purchase is not None:
            purchase.linked_id, purchase.counted = None, True
        return
    funding = db.get(Transaction, bank.transfer_pair_id) if bank.transfer_pair_id else None
    details = dict(bank.details or {})
    bank.merchant_id = details.get("orig_merchant_id", bank.merchant_id)
    for k in LINK_KEYS:
        details.pop(k, None)
    details["no_link"] = True  # ne pas re-rapprocher automatiquement
    bank.details = details
    bank.linked_id = bank.transfer_pair_id = None
    if funding is not None:
        funding.transfer_pair_id = None
    if purchase is not None:
        purchase.linked_id, purchase.counted = None, True
        if funding is None:  # achat synchronisé rapproché directement : ne pas le re-rapprocher
            purchase.details = {**(purchase.details or {}), "no_link": True}
    db.flush()
    db.expire(bank, ["merchant"])
    Categorizer(db).apply([x for x in (bank, purchase) if x is not None])
