from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Category
from app.schemas import CategoryDeleteOut, CategoryIn, CategoryOut, CategoryPatch, CategoryUsage
from app.security import require_auth
from app.services import category_admin as ca
from app.services.planning import category_natures

router = APIRouter(prefix="/api/categories", tags=["catégories"], dependencies=[Depends(require_auth)])


def _out(c: Category, protected: set[int], natures: dict[int, str] | None = None) -> CategoryOut:
    return CategoryOut(
        id=c.id, parent_id=c.parent_id, name=c.name, kind=c.kind, color=c.color, icon=c.icon, protected=c.id in protected,
        nature=c.nature, nature_effective=(natures or {}).get(c.id) if c.kind == "depense" else None,
    )


def _get(db: Session, category_id: int) -> Category:
    c = db.get(Category, category_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Catégorie introuvable")
    return c


@router.get("", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    protected = ca.protected_ids(db)
    cats = db.scalars(select(Category).order_by(Category.parent_id.is_not(None), Category.name)).all()
    natures = category_natures(db)
    return [_out(c, protected, natures) for c in cats]


@router.get("/usage", response_model=list[CategoryUsage])
def category_usage(db: Session = Depends(get_db)):
    return [CategoryUsage(id=cid, **u) for cid, u in ca.usage(db).items()]


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryIn, db: Session = Depends(get_db)):
    try:
        c = ca.create(db, body.name, body.parent_id, body.kind, body.color, body.icon)
    except ca.CategoryError as e:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    db.commit()
    return _out(c, set())


@router.patch("/{category_id}", response_model=CategoryOut)
def patch_category(category_id: int, body: CategoryPatch, db: Session = Depends(get_db)):
    c = _get(db, category_id)
    if body.nature is not None:
        if c.kind != "depense":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La nature ne concerne que les catégories de dépenses")
        c.nature = None if body.nature == "auto" else body.nature
    try:
        ca.update_category(
            db, c, name=body.name, color=body.color, icon=body.icon, kind=body.kind, move=body.move, parent_id=body.parent_id
        )
    except ca.CategoryError as e:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    db.commit()
    return _out(c, ca.protected_ids(db), category_natures(db))


@router.delete("/{category_id}", response_model=CategoryDeleteOut)
def delete_category(category_id: int, move_to: int | None = None, db: Session = Depends(get_db)):
    c = _get(db, category_id)
    try:
        res = ca.delete_category(db, c, move_to)
    except ca.CategoryError as e:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    db.commit()
    return CategoryDeleteOut(**res.__dict__)
