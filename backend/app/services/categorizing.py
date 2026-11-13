"""Application des règles de catégorisation aux opérations en base."""

import json
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.categorize import CompiledRule, find_category, owner_signatures
from app.models import Category, Merchant, Rule, Transaction
from app.seed import INTERNAL_TRANSFER_PATH, category_paths, get_meta, set_meta

USER_RULE_PRIORITY = 10


SERVICE_PRIORITY = 5  # un service passe avant la catégorie générale du vendeur (10)


def load_rules(db: Session) -> list[CompiledRule]:
    rows = db.execute(
        select(Rule, Merchant.name).outerjoin(Merchant, Rule.merchant_id == Merchant.id).order_by(Rule.priority, Rule.id)
    ).all()
    return [
        CompiledRule(
            r.id, r.match_type, r.pattern or "", r.category_id, r.priority,
            merchant=name if r.merchant_id else None, amount_min=r.amount_min_cents, amount_max=r.amount_max_cents,
        )
        for r, name in rows
    ]


def get_owner_signatures(db: Session) -> list[str]:
    return json.loads(get_meta(db, "owner_signatures", "[]"))


def remember_owner(db: Session, holder: str | None) -> None:
    sigs = get_owner_signatures(db)
    new = [s for s in owner_signatures(holder) if s not in sigs]
    if new:
        set_meta(db, "owner_signatures", json.dumps(sigs + new))


class Categorizer:
    """Charge règles et paramètres une fois, puis catégorise autant d'opérations que voulu."""

    def __init__(self, db: Session):
        self.rules = load_rules(db)
        self.signatures = get_owner_signatures(db)
        self.internal_id = category_paths(db).get(INTERNAL_TRANSFER_PATH)
        self.kinds = dict(db.execute(select(Category.id, Category.kind)).all())

    def apply(self, txns: Iterable[Transaction]) -> int:
        changed = 0
        for t in txns:
            if t.category_locked or (t.details or {}).get("virement_interne"):
                continue  # choix manuel, ou virement entre mes comptes (géré par services/transfers)
            # Une opération rapprochée (ex. prélèvement CA payé via PayPal) est catégorisée
            # d'après l'achat réel, pas d'après le libellé « PayPal » de la banque.
            text = (t.details or {}).get("match_text") or t.raw_label
            cat_id, rule = find_category(
                self.rules, text, t.merchant.name if t.merchant else None, self.signatures, self.internal_id, t.amount_cents
            )
            is_transfer = self.kinds.get(cat_id) == "transfert"
            rule_id = rule.id if rule else None
            if cat_id != t.category_id or is_transfer != t.is_transfer or rule_id != t.rule_id:
                t.category_id, t.is_transfer, t.rule_id = cat_id, is_transfer, rule_id
                changed += 1
        return changed


def recategorize(db: Session, merchant_id: int | None = None) -> int:
    """Réapplique les règles à toutes les opérations non verrouillées (ou à un seul marchand)."""
    q = select(Transaction).options(selectinload(Transaction.merchant)).where(Transaction.category_locked.is_(False))
    if merchant_id is not None:
        q = q.where(Transaction.merchant_id == merchant_id)
    return Categorizer(db).apply(db.scalars(q))


def set_merchant_category(db: Session, merchant: Merchant, category_id: int | None) -> int:
    """Crée (ou met à jour) la règle « ce marchand → cette catégorie » et l'applique."""
    rule = db.scalar(select(Rule).where(Rule.match_type == "marchand", Rule.pattern == merchant.name))
    if category_id is None:
        if rule:
            db.delete(rule)
    elif rule:
        rule.category_id = category_id
    else:
        db.add(
            Rule(
                pattern=merchant.name,
                match_type="marchand",
                category_id=category_id,
                priority=USER_RULE_PRIORITY,
                from_correction=True,
            )
        )
    merchant.default_category_id = category_id
    db.flush()
    return recategorize(db, merchant.id)
