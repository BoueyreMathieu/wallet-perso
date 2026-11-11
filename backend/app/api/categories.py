from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Category
from app.schemas import CategoryOut
from app.security import require_auth

router = APIRouter(prefix="/api/categories", tags=["catégories"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    return db.scalars(select(Category).order_by(Category.parent_id.is_not(None), Category.name)).all()
