import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, object_session, selectinload

from app.db import get_db
from app.models import Account, Category, Merchant, PendingTransaction, Rule, Tag, Transaction
from app.schemas import (
    BulkIn,
    ManualTransactionIn,
    PairIn,
    BulkOut,
    ServiceSuggestion,
    MerchantGroupOut,
    RuleOut,
    TransactionOut,
    TransactionPage,
    TransactionPatch,
    UpdatedOut,
)
from app.security import require_auth
from app.connectors.base import stable_hash
from app.services.categorizing import Categorizer, recategorize, set_merchant_category
from app.services.cleanup import delete_transactions
from app.services.reconcile import sync_category, unlink
from app.services import transfers
from app.services.services import bulk_tags, effective_tags, suggest_service, tag_condition

# Infos internes jamais renvoyées à l'interface.
HIDDEN_DETAILS = {"match_text", "orig_merchant_id", "no_link", "role", "virement_interne", "no_pair"}

router = APIRouter(prefix="/api", tags=["opérations"], dependencies=[Depends(require_auth)])


def display_label(t: Transaction) -> str:
    if t.merchant:
        return t.merchant.name
    parts = t.raw_label.split(" | ")
    return parts[1] if len(parts) > 1 else parts[0]


def to_out(t: Transaction, tags: list[dict] | None = None) -> TransactionOut:
    return TransactionOut(
        id=t.id,
        account_id=t.account_id,
        account_name=t.account.name,
        booked_at=t.booked_at,
        amount_cents=t.amount_cents,
        label=display_label(t),
        raw_label=t.raw_label,
        merchant_id=t.merchant_id,
        merchant=t.merchant.name if t.merchant else None,
        category_id=t.category_id,
        category_locked=t.category_locked,
        is_transfer=t.is_transfer,
        note=t.note,
        counted=t.counted,
        linked_id=t.linked_id,
        status=t.status,
        details={k: v for k, v in (t.details or {}).items() if k not in HIDDEN_DETAILS} or None,
        rule_id=t.rule_id,
        source=t.source,
        tags=tags or [],
        transfer_pair_id=t.transfer_pair_id,
        pair_account=_pair_account(t),
        recurring_id=t.recurring_id,
    )


def _pair_account(t: Transaction) -> str | None:
    db = object_session(t)
    return transfers.pair_account_name(db, t) if db is not None else None


def _category_and_children(db: Session, category_id: int) -> list[int]:
    return [category_id, *db.scalars(select(Category.id).where(Category.parent_id == category_id))]


@router.get("/transactions", response_model=TransactionPage)
def list_transactions(
    account_id: int | None = None,
    category_id: int | None = None,
    merchant_id: int | None = None,
    no_merchant: bool = False,
    tag_id: int | None = None,
    uncategorized: bool = False,
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    stmt = select(Transaction).outerjoin(Merchant, Transaction.merchant_id == Merchant.id)
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if category_id is not None:
        stmt = stmt.where(Transaction.category_id.in_(_category_and_children(db, category_id)))
    if merchant_id is not None:
        stmt = stmt.where(Transaction.merchant_id == merchant_id)
    if no_merchant:
        stmt = stmt.where(Transaction.merchant_id.is_(None))
    if tag_id is not None:
        stmt = stmt.where(tag_condition(tag_id))
    if uncategorized:
        stmt = stmt.where(Transaction.category_id.is_(None))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Transaction.raw_label).like(like), func.lower(Merchant.name).like(like)))
    if date_from:
        stmt = stmt.where(Transaction.booked_at >= date_from)
    if date_to:
        stmt = stmt.where(Transaction.booked_at <= date_to)

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.options(selectinload(Transaction.account), selectinload(Transaction.merchant))
        .order_by(Transaction.booked_at.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    tags = effective_tags(db, list(rows))
    return TransactionPage(items=[to_out(t, tags.get(t.id)) for t in rows], total=total or 0)


@router.patch("/transactions/{tx_id}", response_model=UpdatedOut)
def update_transaction(tx_id: int, body: TransactionPatch, db: Session = Depends(get_db)):
    t = db.get(Transaction, tx_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opération introuvable")
    fields = body.model_fields_set
    if body.category_id is not None and db.get(Category, body.category_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Catégorie inconnue")
    manual_fields = fields & {"account_id", "booked_at", "amount_cents", "label", "merchant"}
    if manual_fields:
        if t.source != "manuel":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Seules les opérations saisies à la main peuvent être modifiées ainsi"
            )
        if "account_id" in fields and body.account_id is not None:
            if db.get(Account, body.account_id) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Compte inconnu")
            t.account_id = body.account_id
        if "booked_at" in fields and body.booked_at is not None:
            t.booked_at = body.booked_at
        if "amount_cents" in fields and body.amount_cents:
            t.amount_cents = body.amount_cents
        if "label" in fields and body.label:
            t.raw_label = body.label.strip()
        if "merchant" in fields:
            t.merchant = get_or_create_merchant(db, body.merchant)
        db.flush()
        if not t.category_locked and "category_id" not in fields:
            db.expire(t, ["merchant"])
            Categorizer(db).apply([t])
    if "note" in fields:
        t.note = body.note
    updated = 1
    if "category_id" in fields:
        new_cat = db.get(Category, body.category_id) if body.category_id else None
        if (t.details or {}).get(transfers.MARK) and not (new_cat and new_cat.kind == "transfert"):
            # Catégorie de dépense/revenu sur un virement apparié : ce n'était pas un virement entre mes comptes.
            transfers.unpair(db, t)
        if body.apply_to_merchant and t.merchant:
            t.category_locked = False
            updated = set_merchant_category(db, t.merchant, body.category_id)
        else:
            cat = db.get(Category, body.category_id) if body.category_id else None
            t.category_id = body.category_id
            t.category_locked = body.category_id is not None
            t.is_transfer = bool(cat and cat.kind == "transfert")
            t.rule_id = None
        # Opération rapprochée (CA ↔ PayPal) : les deux côtés gardent la même catégorie.
        if t.linked_id:
            twin = db.get(Transaction, t.linked_id)
            if twin is not None:
                sync_category(t, twin)
                updated += 1
        # Virement entre mes comptes : les deux côtés gardent la même catégorie de transfert.
        if (t.details or {}).get(transfers.MARK) and t.transfer_pair_id:
            twin = db.get(Transaction, t.transfer_pair_id)
            if twin is not None:
                sync_category(t, twin)
                updated += 1
    db.commit()
    return UpdatedOut(updated=updated)


def get_or_create_merchant(db: Session, name: str | None) -> Merchant | None:
    name = (name or "").strip()[:150]
    if not name:
        return None
    # Nom exact d'abord : lower() de SQLite ignore les accents (« É »), celui de PostgreSQL non.
    m = db.scalar(select(Merchant).where(Merchant.name == name))
    if m is None:
        m = db.scalar(select(Merchant).where(func.lower(Merchant.name) == name.lower()))
    if m is None:
        m = Merchant(name=name, aliases=[])
        db.add(m)
        db.flush()
    return m


@router.post("/transactions", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(body: ManualTransactionIn, db: Session = Depends(get_db)):
    """Opération saisie à la main (espèces, oubli, compte sans import…). Elle s'ajoute au solde du compte
    si elle est datée après le dernier solde connu ; un import ultérieur qui la retrouve la fusionne."""
    if db.get(Account, body.account_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Compte inconnu")
    if body.amount_cents == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Le montant ne peut pas être nul")
    cat = db.get(Category, body.category_id) if body.category_id is not None else None
    if body.category_id is not None and cat is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Catégorie inconnue")
    t = Transaction(
        account_id=body.account_id,
        booked_at=body.booked_at,
        amount_cents=body.amount_cents,
        raw_label=body.label.strip(),
        merchant=get_or_create_merchant(db, body.merchant),
        dedup_hash=stable_hash("manuel", uuid.uuid4().hex),
        source="manuel",
        note=body.note,
        is_transfer=False,
        category_locked=False,
        counted=True,
    )
    if body.tag_ids:
        t.tags = list(db.scalars(select(Tag).where(Tag.id.in_(body.tag_ids))))
    db.add(t)
    db.flush()
    if cat is not None:
        t.category_id, t.category_locked, t.is_transfer = cat.id, True, cat.kind == "transfert"
    else:
        Categorizer(db).apply([t])
    db.commit()
    db.refresh(t)
    return to_out(t, effective_tags(db, [t]).get(t.id))


@router.delete("/transactions/{tx_id}", response_model=UpdatedOut)
def delete_transaction(tx_id: int, db: Session = Depends(get_db)):
    """Supprime une opération (une opération importée reviendra si tu réimportes le même fichier)."""
    t = db.get(Transaction, tx_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opération introuvable")
    delete_transactions(db, [t])
    db.commit()
    return UpdatedOut(updated=1)


@router.post("/transactions/bulk", response_model=BulkOut)
def bulk_update(body: BulkIn, db: Session = Depends(get_db)):
    """Actions groupées sur une sélection d'opérations : étiquettes et/ou catégorie."""
    txns = list(db.scalars(select(Transaction).options(selectinload(Transaction.tags)).where(Transaction.id.in_(body.ids))))
    if len(txns) != len(set(body.ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Certaines opérations sont introuvables")
    res = {"updated": 0, "inherited_kept": 0}
    if body.add_tag_ids or body.remove_tag_ids:
        res = bulk_tags(db, txns, body.add_tag_ids, body.remove_tag_ids)
    if body.set_category:
        cat = db.get(Category, body.category_id) if body.category_id is not None else None
        if body.category_id is not None and cat is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Catégorie inconnue")
        for t in txns:
            t.category_id, t.category_locked = body.category_id, body.category_id is not None
            t.is_transfer, t.rule_id = bool(cat and cat.kind == "transfert"), None
            if t.linked_id:
                twin = db.get(Transaction, t.linked_id)
                if twin is not None:
                    sync_category(t, twin)
        res["updated"] = max(res["updated"], len(txns))
    db.commit()
    return BulkOut(**res)


@router.get("/transactions/{tx_id}/service-suggestion", response_model=ServiceSuggestion)
def service_suggestion(tx_id: int, db: Session = Depends(get_db)):
    """Propose un service (mot-clé distinctif) à partir d'une opération."""
    t = db.get(Transaction, tx_id)
    if t is None or t.merchant_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opération introuvable ou sans vendeur")
    return ServiceSuggestion(**suggest_service(db, t))


@router.post("/transactions/{tx_id}/unlink", response_model=UpdatedOut)
def unlink_transaction(tx_id: int, db: Session = Depends(get_db)):
    """Défait un rapprochement CA ↔ PayPal jugé faux."""
    t = db.get(Transaction, tx_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opération introuvable")
    if not t.linked_id and not t.transfer_pair_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Cette opération n'est rapprochée de rien")
    if (t.details or {}).get(transfers.MARK):
        transfers.unpair(db, t)  # virement entre mes comptes
    else:
        unlink(db, t)
    db.commit()
    return UpdatedOut(updated=1)


@router.post("/transactions/pair", response_model=UpdatedOut)
def pair_transactions(body: PairIn, db: Session = Depends(get_db)):
    """Marque deux opérations comme les deux côtés d'un virement entre mes comptes."""
    a, b = (db.get(Transaction, i) for i in body.ids)
    if a is None or b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opération introuvable")
    try:
        transfers.pair_manually(db, a, b)
    except transfers.TransferError as e:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    db.commit()
    return UpdatedOut(updated=2)


@router.post("/transfers/detect", response_model=UpdatedOut)
def detect_transfers(db: Session = Depends(get_db)):
    """Recherche les virements entre mes comptes pas encore appariés."""
    n = transfers.detect(db)
    db.commit()
    return UpdatedOut(updated=n)


@router.get("/transactions/to-categorize", response_model=list[MerchantGroupOut])
def to_categorize(db: Session = Depends(get_db)):
    """Opérations sans catégorie, regroupées par marchand (les plus fréquents d'abord)."""
    rows = db.execute(
        select(
            Transaction.merchant_id,
            Merchant.name,
            func.count(Transaction.id),
            func.sum(Transaction.amount_cents),
            func.max(Transaction.booked_at),
            func.min(Transaction.raw_label),
        )
        .outerjoin(Merchant, Transaction.merchant_id == Merchant.id)
        .where(Transaction.category_id.is_(None))
        .group_by(Transaction.merchant_id, Merchant.name)
        .order_by(func.count(Transaction.id).desc(), func.sum(Transaction.amount_cents))
    ).all()
    return [
        MerchantGroupOut(
            merchant_id=mid, merchant=name, count=n, total_cents=int(total or 0), last_date=last, sample_label=sample
        )
        for mid, name, n, total, last, sample in rows
    ]


@router.get("/rules", response_model=list[RuleOut])
def list_rules(user_only: bool = True, db: Session = Depends(get_db)):
    q = select(Rule).order_by(Rule.priority, Rule.id)
    if user_only:
        q = q.where(Rule.from_correction.is_(True))
    return [RuleOut.model_validate(r, from_attributes=True) for r in db.scalars(q)]


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    r = db.get(Rule, rule_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Règle introuvable")
    db.delete(r)
    db.flush()
    recategorize(db)
    db.commit()


@router.post("/rules/reapply", response_model=UpdatedOut)
def reapply_rules(db: Session = Depends(get_db)):
    updated = recategorize(db)
    db.commit()
    return UpdatedOut(updated=updated)


class PendingOut(BaseModel):
    id: int
    account_id: int
    account_name: str
    booked_at: date
    amount_cents: int
    label: str
    raw_label: str
    category_id: int | None


@router.get("/pending", response_model=list[PendingOut])
def list_pending(account_id: int | None = None, db: Session = Depends(get_db)):
    """Opérations « à venir » vues à la banque (pas encore comptabilisées, hors statistiques)."""
    q = select(PendingTransaction, Account.name).join(Account, PendingTransaction.account_id == Account.id)
    if account_id is not None:
        q = q.where(PendingTransaction.account_id == account_id)
    rows = db.execute(q.order_by(PendingTransaction.booked_at.desc(), PendingTransaction.id)).all()
    return [
        PendingOut(
            id=p.id, account_id=p.account_id, account_name=name, booked_at=p.booked_at, amount_cents=p.amount_cents,
            label=p.merchant or p.raw_label.split(" | ")[0], raw_label=p.raw_label, category_id=p.category_id,
        )
        for p, name in rows
    ]
