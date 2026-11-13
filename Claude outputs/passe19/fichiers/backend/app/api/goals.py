"""Objectifs d'épargne."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Account, Goal
from app.security import require_auth
from app.services.goals import goals_view

router = APIRouter(prefix="/api/goals", tags=["objectifs"], dependencies=[Depends(require_auth)])


class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    icon: str | None = Field(default=None, max_length=8)
    target_cents: int = Field(gt=0)
    target_date: date | None = None
    account_id: int | None = None
    saved_cents: int = Field(default=0, ge=0)
    priority: int = 0


class GoalPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    icon: str | None = Field(default=None, max_length=8)
    target_cents: int | None = Field(default=None, gt=0)
    target_date: date | None = None
    account_id: int | None = None
    saved_cents: int | None = Field(default=None, ge=0)
    priority: int | None = None


def _check_account(db: Session, account_id: int | None) -> None:
    if account_id is not None and db.get(Account, account_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Compte inconnu")


def _one(db: Session, goal_id: int) -> dict:
    return next(g for g in goals_view(db, date.today()) if g["id"] == goal_id)


@router.get("")
def list_goals(db: Session = Depends(get_db)) -> list[dict]:
    return goals_view(db, date.today())


@router.post("", status_code=status.HTTP_201_CREATED)
def create_goal(body: GoalIn, db: Session = Depends(get_db)) -> dict:
    _check_account(db, body.account_id)
    g = Goal(**body.model_dump())
    db.add(g)
    db.commit()
    return _one(db, g.id)


@router.patch("/{goal_id}")
def update_goal(goal_id: int, body: GoalPatch, db: Session = Depends(get_db)) -> dict:
    g = db.get(Goal, goal_id)
    if g is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Objectif introuvable")
    data = body.model_dump(exclude_unset=True)
    if "account_id" in data:
        _check_account(db, data["account_id"])
    for k, v in data.items():
        if k in ("name", "target_cents", "saved_cents", "priority") and v is None:
            continue
        setattr(g, k, v)
    db.commit()
    return _one(db, g.id)


@router.delete("/{goal_id}")
def delete_goal(goal_id: int, db: Session = Depends(get_db)) -> dict:
    g = db.get(Goal, goal_id)
    if g is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Objectif introuvable")
    db.delete(g)
    db.commit()
    return {"ok": True}
