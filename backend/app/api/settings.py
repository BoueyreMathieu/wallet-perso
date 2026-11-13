"""Paramètres : ton identité de titulaire (noms qui désignent tes virements)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.security import require_auth
from app.services import owner
from app.services.categorizing import get_owner_signatures

router = APIRouter(prefix="/api/settings", tags=["paramètres"], dependencies=[Depends(require_auth)])


class OwnerOut(BaseModel):
    signatures: list[str]
    matching_merchants: list[str]  # vendeurs reconnus comme « toi » → virements internes
    operations: int


class OwnerIn(BaseModel):
    signatures: list[str] = Field(max_length=10)


def _state(db: Session, sigs: list[str]) -> OwnerOut:
    found = owner.matching_merchants(db, sigs)
    return OwnerOut(signatures=sigs, matching_merchants=sorted(m.name for m in found), operations=owner.operations_count(db, found))


@router.get("/owner", response_model=OwnerOut)
def get_owner(db: Session = Depends(get_db)):
    return _state(db, get_owner_signatures(db))


@router.post("/owner/preview", response_model=OwnerOut)
def preview_owner(body: OwnerIn, db: Session = Depends(get_db)):
    return _state(db, owner.clean(body.signatures))


@router.put("/owner", response_model=OwnerOut)
def save_owner(body: OwnerIn, db: Session = Depends(get_db)):
    sigs = owner.set_signatures(db, body.signatures)
    db.commit()
    return _state(db, sigs)
