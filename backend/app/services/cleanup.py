"""Réinitialisations et suppressions de données (imports, comptes, catégorisations, marchands)."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    Account,
    AppMeta,
    BalanceSnapshot,
    PendingTransaction,
    Budget,
    Category,
    Connection,
    Goal,
    Holding,
    ImportBatch,
    Merchant,
    RecurringSeries,
    Rule,
    Transaction,
    merchant_tag,
    rule_tag,
    transaction_tag,
)
from app.services.categorizing import Categorizer, recategorize
from app.services.reconcile import LINK_KEYS


def _is_forced(t: Transaction) -> bool:
    """Catégorie posée par l'import lui-même (ex. approvisionnement PayPal) : on ne la déverrouille pas."""
    return (t.details or {}).get("role") == "approvisionnement"


def _restore_bank_side(t: Transaction) -> None:
    details = dict(t.details or {})
    if "orig_merchant_id" in details:
        t.merchant_id = details["orig_merchant_id"]
    for k in LINK_KEYS:
        details.pop(k, None)
    t.details = details or None


def delete_transactions(db: Session, txns: list[Transaction]) -> int:
    """Supprime des opérations en détachant proprement leurs jumelles (rapprochements PayPal)."""
    ids = {t.id for t in txns}
    survivors: list[Transaction] = []
    for t in txns:
        for twin_id in {t.linked_id, t.transfer_pair_id} - {None}:
            if twin_id in ids:
                continue
            twin = db.get(Transaction, twin_id)
            if twin is None:
                continue
            if twin.linked_id == t.id:
                twin.linked_id = None
            if twin.transfer_pair_id == t.id:
                twin.transfer_pair_id = None
            if twin.account.type == "paypal":
                if not _is_forced(twin):
                    twin.counted = True
            else:
                _restore_bank_side(twin)
            survivors.append(twin)
    for t in txns:
        db.delete(t)
    db.flush()
    for s in survivors:
        db.expire(s, ["merchant"])
    Categorizer(db).apply([s for s in survivors if s.id not in ids])
    return len(txns)


def undo_import(db: Session, batch: ImportBatch) -> int:
    txns = db.scalars(select(Transaction).where(Transaction.import_batch_id == batch.id)).all()
    n = delete_transactions(db, list(txns))
    db.delete(batch)
    return n


def clear_account(db: Session, acc: Account) -> int:
    txns = db.scalars(select(Transaction).where(Transaction.account_id == acc.id)).all()
    n = delete_transactions(db, list(txns))
    db.execute(delete(BalanceSnapshot).where(BalanceSnapshot.account_id == acc.id))
    db.execute(delete(PendingTransaction).where(PendingTransaction.account_id == acc.id))
    db.execute(delete(ImportBatch).where(ImportBatch.account_id == acc.id))
    # Récurrents détectés sur ce compte : ils n'ont plus d'opérations (les déclarés à la main restent).
    db.execute(delete(RecurringSeries).where(RecurringSeries.account_id == acc.id, RecurringSeries.source == "auto"))
    return n


def delete_account(db: Session, acc: Account) -> int:
    n = clear_account(db, acc)
    db.execute(delete(Holding).where(Holding.account_id == acc.id))
    db.execute(delete(RecurringSeries).where(RecurringSeries.account_id == acc.id))
    db.delete(acc)
    return n


def _unlock(db: Session, where) -> None:
    for t in db.scalars(select(Transaction).where(Transaction.category_locked.is_(True), where)):
        if not _is_forced(t):
            t.category_locked = False


def reset_merchant(db: Session, m: Merchant) -> int:
    """Oublie la catégorie choisie pour ce vendeur (et les corrections sur ses opérations)."""
    db.execute(delete(Rule).where(Rule.match_type == "marchand", Rule.pattern == m.name))
    m.default_category_id = None
    _unlock(db, Transaction.merchant_id == m.id)
    db.flush()
    return recategorize(db, m.id)


def reset_category(db: Session, category_id: int) -> int:
    """Oublie tes choix pour une catégorie (et ses sous-catégories)."""
    ids = [category_id, *db.scalars(select(Category.id).where(Category.parent_id == category_id))]
    db.execute(delete(Rule).where(Rule.from_correction.is_(True), Rule.category_id.in_(ids)))
    for m in db.scalars(select(Merchant).where(Merchant.default_category_id.in_(ids))):
        m.default_category_id = None
    _unlock(db, Transaction.category_id.in_(ids))
    db.flush()
    return recategorize(db)


def reset_all_categorization(db: Session) -> int:
    db.execute(delete(Rule).where(Rule.from_correction.is_(True)))
    for m in db.scalars(select(Merchant).where(Merchant.default_category_id.is_not(None))):
        m.default_category_id = None
    _unlock(db, Transaction.id.is_not(None))
    db.flush()
    return recategorize(db)


def wipe_all(db: Session, keep_accounts: bool) -> None:
    """Efface toutes les données importées. Catégories, règles par défaut et étiquettes sont conservées."""
    db.execute(delete(transaction_tag))
    db.execute(delete(merchant_tag))
    db.execute(delete(rule_tag).where(rule_tag.c.rule_id.in_(select(Rule.id).where(Rule.from_correction.is_(True)))))
    for model in (PendingTransaction, Transaction, ImportBatch, BalanceSnapshot, RecurringSeries, Budget, Goal, Holding):
        db.execute(delete(model))
    db.execute(delete(Rule).where(Rule.from_correction.is_(True)))
    db.execute(delete(Merchant))
    db.execute(delete(AppMeta).where(AppMeta.key == "owner_signatures"))
    if not keep_accounts:
        db.execute(delete(Account))
        db.execute(delete(Connection))
    else:
        for acc in db.scalars(select(Account)):
            acc.external_id = None


# --- Vendeurs : renommer / fusionner ----------------------------------------------


def merge_merchants(db: Session, src: Merchant, dst: Merchant) -> int:
    """Fusionne src dans dst (opérations, alias, règle). src est supprimé."""
    moved = 0
    for t in db.scalars(select(Transaction).where(Transaction.merchant_id == src.id)):
        t.merchant_id = dst.id
        moved += 1
    for t in db.scalars(select(Transaction).where(Transaction.details.is_not(None))):
        if (t.details or {}).get("orig_merchant_id") == src.id:
            t.details = {**t.details, "orig_merchant_id": dst.id}
    dst.aliases = sorted(set((dst.aliases or []) + (src.aliases or [])))
    dst.tags = list({t.id: t for t in [*dst.tags, *src.tags]}.values())
    for service in db.scalars(select(Rule).where(Rule.merchant_id == src.id)):
        service.merchant_id = dst.id
    src_rule = db.scalar(select(Rule).where(Rule.match_type == "marchand", Rule.pattern == src.name))
    dst_rule = db.scalar(select(Rule).where(Rule.match_type == "marchand", Rule.pattern == dst.name))
    if src_rule is not None:
        if dst_rule is None:
            src_rule.pattern = dst.name
        else:
            db.delete(src_rule)
    if dst.default_category_id is None:
        dst.default_category_id = src.default_category_id
    db.flush()
    db.delete(src)
    db.flush()
    recategorize(db, dst.id)
    return moved


def rename_merchant(db: Session, m: Merchant, new_name: str) -> Merchant:
    """Renomme ; si un vendeur porte déjà ce nom, les deux sont fusionnés."""
    new_name = new_name.strip()[:150]
    if new_name == m.name:
        return m
    existing = db.scalar(select(Merchant).where(Merchant.name == new_name))
    if existing is not None:
        merge_merchants(db, m, existing)
        return existing
    rule = db.scalar(select(Rule).where(Rule.match_type == "marchand", Rule.pattern == m.name))
    if rule is not None:
        rule.pattern = new_name
    m.name = new_name
    db.flush()
    return m
