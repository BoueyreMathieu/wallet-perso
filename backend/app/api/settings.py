"""Paramètres : ton identité de titulaire (noms qui désignent tes virements)."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.security import require_auth
from app.seed import get_meta, set_meta
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


# --- Préférences : accueil personnalisé (par plateforme), jour de paie -----------------------------------------

PLATFORMS = ("web", "mobile")


class HomeCard(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    hidden: bool = False


class HomeLayout(BaseModel):
    cards: list[HomeCard] = Field(max_length=50)


@router.get("/home-layout")
def get_home_layout(platform: str = Query(default="web"), db: Session = Depends(get_db)) -> dict:
    """Disposition de l'accueil : une pour l'ordinateur (web), une pour le téléphone (mobile). null = par défaut."""
    if platform not in PLATFORMS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "platform : web ou mobile")
    raw = get_meta(db, f"home_layout_{platform}")
    try:
        return {"platform": platform, "cards": json.loads(raw)["cards"] if raw else None}
    except (ValueError, KeyError, TypeError):
        return {"platform": platform, "cards": None}


@router.put("/home-layout")
def put_home_layout(body: HomeLayout, platform: str = Query(default="web"), db: Session = Depends(get_db)) -> dict:
    if platform not in PLATFORMS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "platform : web ou mobile")
    set_meta(db, f"home_layout_{platform}", json.dumps({"cards": [c.model_dump() for c in body.cards]}))
    db.commit()
    return {"platform": platform, "cards": [c.model_dump() for c in body.cards]}


@router.delete("/home-layout")
def reset_home_layout(platform: str = Query(default="web"), db: Session = Depends(get_db)) -> dict:
    if platform not in PLATFORMS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "platform : web ou mobile")
    set_meta(db, f"home_layout_{platform}", "")
    db.commit()
    return {"platform": platform, "cards": None}


class PaydayIn(BaseModel):
    day: int | None = Field(default=None, ge=1, le=31)  # null = automatique (d'après l'historique)


@router.get("/payday")
def get_payday(db: Session = Depends(get_db)) -> dict:
    raw = get_meta(db, "payday")
    return {"day": int(raw) if raw and raw.isdigit() else None}


@router.put("/payday")
def put_payday(body: PaydayIn, db: Session = Depends(get_db)) -> dict:
    set_meta(db, "payday", str(body.day) if body.day else "")
    db.commit()
    return {"day": body.day}
