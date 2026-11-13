"""Conseils d'optimisation."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.security import require_auth
from app.services import advice

router = APIRouter(prefix="/api", tags=["conseils"], dependencies=[Depends(require_auth)])


class DismissIn(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    days: int = Field(default=30, ge=1, le=365)


@router.get("/advice")
def get_advice(db: Session = Depends(get_db)) -> dict:
    items = advice.list_advice(db, date.today())
    return {"items": [a.to_dict() for a in items], "total_gain_cents": sum(a.gain_monthly_cents for a in items)}


@router.post("/advice/dismiss")
def dismiss_advice(body: DismissIn, db: Session = Depends(get_db)) -> dict:
    advice.dismiss(db, body.id, body.days, date.today())
    return {"ok": True}
