from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, case, delete, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Tag, Transaction, merchant_tag, rule_tag, transaction_tag
from app.schemas import TagIn, TagOut, UpdatedOut
from app.security import require_auth
from app.services.services import tag_condition

router = APIRouter(prefix="/api/tags", tags=["étiquettes"], dependencies=[Depends(require_auth)])


def _out(db: Session, tag: Tag) -> TagOut:
    real = and_(Transaction.counted.is_(True), Transaction.is_transfer.is_(False), Transaction.amount_cents < 0)
    count, spent = db.execute(
        select(func.count(Transaction.id), func.coalesce(func.sum(case((real, -Transaction.amount_cents), else_=0)), 0)).where(
            tag_condition(tag.id)
        )
    ).one()
    merchants = db.scalar(select(func.count()).select_from(merchant_tag).where(merchant_tag.c.tag_id == tag.id))
    services = db.scalar(select(func.count()).select_from(rule_tag).where(rule_tag.c.tag_id == tag.id))
    return TagOut(id=tag.id, name=tag.name, color=tag.color, transactions=count, spent_cents=int(spent), merchants=merchants, services=services)


def _get(db: Session, tag_id: int) -> Tag:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Étiquette introuvable")
    return tag


def _check_unique(db: Session, name: str, exclude: int | None = None) -> None:
    other = db.scalar(select(Tag).where(func.lower(Tag.name) == name.strip().lower()))
    if other is not None and other.id != exclude:
        raise HTTPException(status.HTTP_409_CONFLICT, f"L'étiquette « {other.name} » existe déjà")


@router.get("", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db)):
    return [_out(db, t) for t in db.scalars(select(Tag).order_by(func.lower(Tag.name)))]


@router.post("", response_model=TagOut, status_code=status.HTTP_201_CREATED)
def create_tag(body: TagIn, db: Session = Depends(get_db)):
    _check_unique(db, body.name)
    tag = Tag(name=body.name.strip(), color=body.color)
    db.add(tag)
    db.commit()
    return _out(db, tag)


@router.patch("/{tag_id}", response_model=TagOut)
def update_tag(tag_id: int, body: TagIn, db: Session = Depends(get_db)):
    tag = _get(db, tag_id)
    _check_unique(db, body.name, exclude=tag.id)
    tag.name, tag.color = body.name.strip(), body.color
    db.commit()
    return _out(db, tag)


@router.delete("/{tag_id}", response_model=UpdatedOut)
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    """Supprime l'étiquette partout (opérations, vendeurs, services). Les opérations ne sont pas touchées."""
    tag = _get(db, tag_id)
    for link in (transaction_tag, merchant_tag, rule_tag):
        db.execute(delete(link).where(link.c.tag_id == tag.id))
    db.delete(tag)
    db.commit()
    return UpdatedOut(updated=1)
