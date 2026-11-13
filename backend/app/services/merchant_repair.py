"""Réparation : vendeurs nommés d'après un libellé bancaire générique (« Paiement Par Carte X1234 … »).

Avant le nettoyage des libellés (app/label_cleaning.py), la synchro créait des vendeurs comme
« Paiement Par Carte X1234 Monop 01/11 » — et la fusion des vendeurs similaires pouvait en regrouper
de très différents. On recalcule le vendeur de chaque opération concernée à partir de son libellé,
on reporte la catégorie choisie quand c'est sans ambiguïté, puis on supprime les vendeurs devenus vides.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.label_cleaning import is_generic
from app.models import Merchant, Rule, Transaction
from app.services.categorizing import Categorizer, set_merchant_category
from app.services.merchant_resolver import MerchantResolver


def fix_generic_merchants(db: Session) -> int:
    generic = [m for m in db.scalars(select(Merchant)) if is_generic(m.name)]
    if not generic:
        return 0
    ids = {m.id for m in generic}
    txs = list(
        db.scalars(select(Transaction).options(selectinload(Transaction.merchant)).where(Transaction.merchant_id.in_(ids)))
    )
    resolve = MerchantResolver(db)
    old_category = {m.id: m.default_category_id for m in generic}
    carried: dict[int, set[int]] = defaultdict(set)  # nouveau vendeur → catégories choisies sur les anciens
    changed: list[Transaction] = []
    for t in txs:
        if (t.details or {}).get("via"):
            continue  # ligne bancaire rapprochée d'un achat PayPal : vendeur déjà le bon
        first = t.raw_label.split(" | ")[0]
        new = resolve(first) if is_generic(first) else None
        if new is None:
            new = resolve(t.merchant.name if t.merchant else None)
        if new is not None and new.id in ids:
            continue
        old_id = t.merchant_id
        t.merchant = new
        changed.append(t)
        if new is not None and old_id is not None and old_category.get(old_id):
            carried[id(new)].add(old_category[old_id])  # id() : le nouveau vendeur n'a peut-être pas encore d'id
    db.flush()

    # Catégorie choisie sur les anciens vendeurs → reportée si une seule et le nouveau n'en a pas.
    for t in changed:
        m = t.merchant
        if m is not None and m.default_category_id is None and len(carried.get(id(m), ())) == 1:
            set_merchant_category(db, m, next(iter(carried[id(m)])))
            carried.pop(id(m), None)

    # Vendeurs génériques devenus vides : supprimés avec leurs règles.
    still_used = set(db.scalars(select(Transaction.merchant_id).where(Transaction.merchant_id.in_(ids))))
    for m in generic:
        if m.id in still_used:
            continue
        db.execute(delete(Rule).where(Rule.merchant_id == m.id))
        db.execute(delete(Rule).where(Rule.match_type == "marchand", Rule.pattern == m.name))
        m.tags = []
        db.flush()
        db.delete(m)
    db.flush()
    Categorizer(db).apply([t for t in changed if not t.category_locked])
    db.flush()
    return len(changed)
