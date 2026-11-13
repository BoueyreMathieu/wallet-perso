from collections import Counter, defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.regex_safety import check_regex
from app.models import Category, Merchant, Rule, Tag, Transaction, merchant_tag, rule_tag
from app.schemas import CategoryAssign, ServiceIn, ServiceOut, ServicePatch, TagIds, UpdatedOut
from app.security import require_auth
from app.services.categorizing import recategorize, set_merchant_category
from app.services.cleanup import merge_merchants, rename_merchant, reset_merchant
from app.services import merchant_merge
from app.services.services import save_service

router = APIRouter(prefix="/api", tags=["vendeurs"], dependencies=[Depends(require_auth)])


class CategoryShare(BaseModel):
    category_id: int | None
    count: int
    spent_cents: int
    received_cents: int


class MerchantStatsOut(BaseModel):
    id: int
    name: str
    category_id: int | None  # catégorie générale du vendeur
    category_chosen: bool  # True : choisie par toi ; False : déduite
    categories: list[CategoryShare]  # toutes les catégories de ses opérations sur la période
    services: int
    tag_ids: list[int]
    count: int
    spent_cents: int  # dépenses comptées (montant positif)
    received_cents: int
    last_date: date | None


class MerchantRename(BaseModel):
    name: str = Field(min_length=1, max_length=150)


class MerchantMerge(BaseModel):
    into_id: int


class ServiceShare(BaseModel):
    rule_id: int | None
    label: str
    count: int
    spent_cents: int
    received_cents: int


class Breakdown(BaseModel):
    by_service: list[ServiceShare]
    by_category: list[CategoryShare]


def _get(db: Session, merchant_id: int) -> Merchant:
    m = db.get(Merchant, merchant_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vendeur introuvable")
    return m


def _period(date_from: date | None, date_to: date | None) -> list:
    cond = []
    if date_from:
        cond.append(Transaction.booked_at >= date_from)
    if date_to:
        cond.append(Transaction.booked_at <= date_to)
    return cond


_REAL = and_(Transaction.counted.is_(True), Transaction.is_transfer.is_(False))
_SPENT = func.coalesce(func.sum(case((and_(_REAL, Transaction.amount_cents < 0), -Transaction.amount_cents), else_=0)), 0)
_RECEIVED = func.coalesce(func.sum(case((and_(_REAL, Transaction.amount_cents > 0), Transaction.amount_cents), else_=0)), 0)


@router.get("/merchants", response_model=list[MerchantStatsOut])
def list_merchants(
    date_from: date | None = None,
    date_to: date | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    """Vendeurs avec ce que tu leur as versé / reçu sur la période (opérations comptées uniquement)."""
    period = _period(date_from, date_to)
    rows = db.execute(
        select(Merchant.id, Merchant.name, func.count(Transaction.id), _SPENT, _RECEIVED, func.max(Transaction.booked_at))
        .outerjoin(Transaction, and_(Transaction.merchant_id == Merchant.id, *period))
        .group_by(Merchant.id, Merchant.name)
    ).all()

    shares: dict[int, list[CategoryShare]] = defaultdict(list)
    for mid, cid, n, spent, received in db.execute(
        select(Transaction.merchant_id, Transaction.category_id, func.count(), _SPENT, _RECEIVED)
        .where(Transaction.merchant_id.is_not(None), *period)
        .group_by(Transaction.merchant_id, Transaction.category_id)
    ):
        shares[mid].append(CategoryShare(category_id=cid, count=n, spent_cents=int(spent), received_cents=int(received)))

    chosen = dict(db.execute(select(Rule.pattern, Rule.category_id).where(Rule.match_type == "marchand")).all())
    services = Counter(db.scalars(select(Rule.merchant_id).where(Rule.merchant_id.is_not(None))))
    tags = defaultdict(list)
    for mid, tid in db.execute(select(merchant_tag.c.merchant_id, merchant_tag.c.tag_id)):
        tags[mid].append(tid)

    out = []
    for mid, name, count, spent, received, last in rows:
        if count == 0 and not include_inactive:
            continue
        cats = sorted(shares[mid], key=lambda c: (-c.spent_cents, -c.count))
        cat = chosen.get(name)
        main = cat if cat is not None else next((c.category_id for c in sorted(cats, key=lambda c: -c.count) if c.category_id), None)
        out.append(
            MerchantStatsOut(
                id=mid, name=name, category_id=main, category_chosen=cat is not None, categories=cats,
                services=services[mid], tag_ids=sorted(tags[mid]), count=count, spent_cents=int(spent),
                received_cents=int(received), last_date=last,
            )
        )
    out.sort(key=lambda m: (-m.spent_cents, -m.count, m.name.lower()))
    return out


@router.get("/merchants/{merchant_id}/breakdown", response_model=Breakdown)
def breakdown(merchant_id: int, date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db)):
    """Répartition des opérations d'un vendeur par service et par catégorie."""
    _get(db, merchant_id)
    period = _period(date_from, date_to)
    base = [Transaction.merchant_id == merchant_id, *period]
    labels = dict(db.execute(select(Rule.id, Rule.label).where(Rule.merchant_id == merchant_id)).all())
    by_service = [
        ServiceShare(
            rule_id=rid if rid in labels else None,
            label=(labels.get(rid) or "Service sans nom") if rid in labels else "Hors services",
            count=n, spent_cents=int(s), received_cents=int(r),
        )
        for rid, n, s, r in db.execute(
            select(Transaction.rule_id, func.count(), _SPENT, _RECEIVED).where(*base).group_by(Transaction.rule_id)
        )
    ]
    # Les opérations hors services peuvent venir de plusieurs règles : on les regroupe.
    merged: dict[int | None, ServiceShare] = {}
    for s in by_service:
        if s.rule_id in merged:
            m = merged[s.rule_id]
            m.count, m.spent_cents, m.received_cents = m.count + s.count, m.spent_cents + s.spent_cents, m.received_cents + s.received_cents
        else:
            merged[s.rule_id] = s
    by_category = [
        CategoryShare(category_id=cid, count=n, spent_cents=int(s), received_cents=int(r))
        for cid, n, s, r in db.execute(
            select(Transaction.category_id, func.count(), _SPENT, _RECEIVED).where(*base).group_by(Transaction.category_id)
        )
    ]
    key = lambda x: (-x.spent_cents, -x.count)  # noqa: E731
    return Breakdown(by_service=sorted(merged.values(), key=key), by_category=sorted(by_category, key=key))


@router.post("/merchants/{merchant_id}/category", response_model=UpdatedOut)
def categorize_merchant(merchant_id: int, body: CategoryAssign, db: Session = Depends(get_db)):
    m = _get(db, merchant_id)
    if body.category_id is not None and db.get(Category, body.category_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Catégorie inconnue")
    updated = set_merchant_category(db, m, body.category_id)
    db.commit()
    return UpdatedOut(updated=updated)


@router.post("/merchants/{merchant_id}/reset", response_model=UpdatedOut)
def reset(merchant_id: int, db: Session = Depends(get_db)):
    """Oublie la catégorie générale choisie pour ce vendeur (ses services sont conservés)."""
    updated = reset_merchant(db, _get(db, merchant_id))
    db.commit()
    return UpdatedOut(updated=updated)


@router.patch("/merchants/{merchant_id}")
def rename(merchant_id: int, body: MerchantRename, db: Session = Depends(get_db)) -> dict:
    """Renomme le vendeur. Si le nom existe déjà, les deux vendeurs sont fusionnés."""
    m = rename_merchant(db, _get(db, merchant_id), body.name)
    db.commit()
    return {"id": m.id, "name": m.name, "merged": m.id != merchant_id}


class SimilarMerchant(BaseModel):
    id: int
    name: str
    count: int


class SimilarGroup(BaseModel):
    merchants: list[SimilarMerchant]
    proposed_id: int


class GroupMerge(BaseModel):
    ids: list[int] = Field(min_length=2)
    target_id: int
    name: str | None = Field(default=None, max_length=150)


class GroupIgnore(BaseModel):
    ids: list[int] = Field(min_length=2)


@router.get("/merchants/similar", response_model=list[SimilarGroup])
def similar_merchants(db: Session = Depends(get_db)):
    """Vendeurs probablement identiques (même début de nom), à confirmer."""
    return merchant_merge.suggestions(db)


@router.post("/merchants/auto-merge", response_model=UpdatedOut)
def auto_merge(db: Session = Depends(get_db)):
    """Fusionne tout de suite les vendeurs sûrement identiques (troncature / référence près)."""
    n = merchant_merge.auto_merge(db)
    db.commit()
    return UpdatedOut(updated=n)


@router.post("/merchants/merge-group", response_model=UpdatedOut)
def merge_group(body: GroupMerge, db: Session = Depends(get_db)):
    if body.target_id not in body.ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Le vendeur gardé doit faire partie de la sélection")
    group = [_get(db, i) for i in dict.fromkeys(body.ids)]
    moved = merchant_merge.merge_group(db, group, _get(db, body.target_id), body.name)
    db.commit()
    return UpdatedOut(updated=moved)


@router.post("/merchants/similar/ignore", response_model=UpdatedOut)
def ignore_similar(body: GroupIgnore, db: Session = Depends(get_db)):
    """« Ce ne sont pas les mêmes » : la suggestion ne revient plus."""
    merchant_merge.ignore(db, body.ids)
    db.commit()
    return UpdatedOut(updated=len(body.ids))


@router.post("/merchants/{merchant_id}/merge", response_model=UpdatedOut)
def merge(merchant_id: int, body: MerchantMerge, db: Session = Depends(get_db)):
    if body.into_id == merchant_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Impossible de fusionner un vendeur avec lui-même")
    moved = merge_merchants(db, _get(db, merchant_id), _get(db, body.into_id))
    db.commit()
    return UpdatedOut(updated=moved)


@router.put("/merchants/{merchant_id}/tags", response_model=UpdatedOut)
def set_merchant_tags(merchant_id: int, body: TagIds, db: Session = Depends(get_db)):
    """Étiquettes du vendeur : héritées par toutes ses opérations."""
    m = _get(db, merchant_id)
    m.tags = list(db.scalars(select(Tag).where(Tag.id.in_(body.tag_ids))))
    db.commit()
    return UpdatedOut(updated=len(m.tags))


# --- Services ------------------------------------------------------------------------


def _service_out(db: Session, r: Rule) -> ServiceOut:
    tag_ids = sorted(db.scalars(select(rule_tag.c.tag_id).where(rule_tag.c.rule_id == r.id)))
    return ServiceOut(
        id=r.id, merchant_id=r.merchant_id, label=r.label, pattern=r.pattern, match_type=r.match_type,
        amount_min_cents=r.amount_min_cents, amount_max_cents=r.amount_max_cents, category_id=r.category_id, tag_ids=tag_ids,
    )


def _check_service(db: Session, data: dict) -> None:
    if data.get("category_id") is not None and db.get(Category, data["category_id"]) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Catégorie inconnue")
    lo, hi = data.get("amount_min_cents"), data.get("amount_max_cents")
    if lo is not None and hi is not None and lo > hi:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Montant minimum supérieur au maximum")
    if data.get("match_type") == "regex":
        problem = check_regex(data.get("pattern") or "")
        if problem:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)


@router.get("/merchants/{merchant_id}/services", response_model=list[ServiceOut])
def list_services(merchant_id: int, db: Session = Depends(get_db)):
    _get(db, merchant_id)
    rules = db.scalars(select(Rule).where(Rule.merchant_id == merchant_id).order_by(Rule.label, Rule.id))
    return [_service_out(db, r) for r in rules]


@router.post("/merchants/{merchant_id}/services", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
def create_service(merchant_id: int, body: ServiceIn, db: Session = Depends(get_db)):
    _get(db, merchant_id)
    data = body.model_dump()
    _check_service(db, data)
    if not data["pattern"].strip() and data["amount_min_cents"] is None and data["amount_max_cents"] is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Indique un mot-clé ou un montant pour reconnaître ce service")
    rule = Rule(merchant_id=merchant_id, pattern="")
    save_service(db, rule, data)
    db.commit()
    return _service_out(db, rule)


@router.patch("/services/{rule_id}", response_model=ServiceOut)
def update_service(rule_id: int, body: ServicePatch, db: Session = Depends(get_db)):
    rule = db.get(Rule, rule_id)
    if rule is None or rule.merchant_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service introuvable")
    data = body.model_dump(exclude_unset=True)
    _check_service(db, {"match_type": rule.match_type, "pattern": rule.pattern, **data})
    save_service(db, rule, data)
    db.commit()
    return _service_out(db, rule)


@router.delete("/services/{rule_id}", response_model=UpdatedOut)
def delete_service(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(Rule, rule_id)
    if rule is None or rule.merchant_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service introuvable")
    merchant_id = rule.merchant_id
    db.delete(rule)
    db.flush()
    updated = recategorize(db, merchant_id)
    db.commit()
    return UpdatedOut(updated=updated)
