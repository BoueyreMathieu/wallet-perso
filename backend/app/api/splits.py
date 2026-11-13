"""Découper une opération (un ticket de supermarché : courses + maison…) et dépenses partagées / avances.

- Les **parts** remplacent l'opération dans les statistiques (catégories, budgets, prévisions) ; le solde du compte,
  lui, compte l'opération d'origine (une seule fois). L'opération d'origine passe « non comptée ».
- Une part **avancée pour quelqu'un** (resto payé pour 3…) n'est pas une dépense : elle va dans « On me doit ».
  Quand la personne rembourse, le virement reçu est rattaché à l'avance et ne compte pas comme un revenu.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import stable_hash
from app.db import get_db
from app.models import Category, Transaction
from app.security import require_auth
from app.services.balances import SPLIT_SOURCE

router = APIRouter(prefix="/api", tags=["découpage"], dependencies=[Depends(require_auth)])


class PartIn(BaseModel):
    amount_cents: int
    category_id: int | None = None
    note: str | None = Field(default=None, max_length=200)
    person: str | None = Field(default=None, max_length=80)  # renseigné : part avancée pour cette personne


class SplitIn(BaseModel):
    parts: list[PartIn] = Field(min_length=2, max_length=10)


class SettleIn(BaseModel):
    transaction_id: int | None = None  # le remboursement reçu (ou rien : réglé en espèces, par exemple)


def _get(db: Session, tx_id: int) -> Transaction:
    t = db.get(Transaction, tx_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opération introuvable")
    return t


def parts_of(db: Session, t: Transaction) -> list[Transaction]:
    rows = db.scalars(select(Transaction).where(
        Transaction.source == SPLIT_SOURCE, Transaction.account_id == t.account_id, Transaction.booked_at == t.booked_at,
    ).order_by(Transaction.id)).all()
    return [p for p in rows if (p.details or {}).get("part_de") == t.id]


def _summary(db: Session, t: Transaction) -> dict:
    return {
        "transaction_id": t.id, "amount_cents": t.amount_cents, "split": bool((t.details or {}).get("decoupee")),
        "parts": [{"id": p.id, "amount_cents": p.amount_cents, "category_id": p.category_id, "note": p.note,
                   "person": ((p.details or {}).get("avance") or {}).get("person")} for p in parts_of(db, t)],
    }


@router.get("/transactions/{tx_id}/split")
def get_split(tx_id: int, db: Session = Depends(get_db)) -> dict:
    return _summary(db, _get(db, tx_id))


@router.post("/transactions/{tx_id}/split")
def split_transaction(tx_id: int, body: SplitIn, db: Session = Depends(get_db)) -> dict:
    t = _get(db, tx_id)
    if t.source == SPLIT_SOURCE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "C'est déjà une part : découpe l'opération d'origine")
    if t.is_transfer:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Un virement entre tes comptes ne se découpe pas")
    if not t.counted and not (t.details or {}).get("decoupee"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Cette opération n'est pas comptée (doublon rapproché) : découpe l'autre")
    if sum(p.amount_cents for p in body.parts) != t.amount_cents:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"La somme des parts doit faire {t.amount_cents / 100:.2f} €".replace(".", ","))
    if any(p.amount_cents == 0 or (p.amount_cents > 0) != (t.amount_cents > 0) for p in body.parts):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Chaque part doit être non nulle et du même sens que l'opération")
    for p in body.parts:
        if p.category_id is not None and db.get(Category, p.category_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Catégorie inconnue")
    for old in parts_of(db, t):
        db.delete(old)
    db.flush()
    for i, p in enumerate(body.parts):
        person = (p.person or "").strip() or None
        details: dict = {"part_de": t.id}
        if person:
            details["avance"] = {"person": person, "settled": False, "settled_by": None, "settled_on": None}
        db.add(Transaction(
            account_id=t.account_id, booked_at=t.booked_at, amount_cents=p.amount_cents, raw_label=t.raw_label,
            merchant_id=t.merchant_id, dedup_hash=stable_hash("decoupe", t.id, i, uuid.uuid4().hex), source=SPLIT_SOURCE,
            note=p.note, is_transfer=False, category_id=p.category_id, category_locked=True, counted=person is None, details=details,
        ))
    t.counted = False
    t.details = {**(t.details or {}), "decoupee": True}
    db.commit()
    return _summary(db, t)


@router.delete("/transactions/{tx_id}/split")
def unsplit_transaction(tx_id: int, db: Session = Depends(get_db)) -> dict:
    t = _get(db, tx_id)
    for p in parts_of(db, t):
        settled_by = ((p.details or {}).get("avance") or {}).get("settled_by")
        if settled_by:
            _release_refund(db, settled_by)
        db.delete(p)
    t.counted = True
    t.details = {k: v for k, v in (t.details or {}).items() if k != "decoupee"} or None
    db.commit()
    return _summary(db, t)


# --- On me doit (avances) ----------------------------------------------------------------------------


def _release_refund(db: Session, tx_id: int) -> None:
    r = db.get(Transaction, tx_id)
    if r is not None and (r.details or {}).get("remboursement_de"):
        r.counted = True
        r.details = {k: v for k, v in (r.details or {}).items() if k != "remboursement_de"} or None


@router.get("/advances")
def list_advances(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Transaction).where(Transaction.source == SPLIT_SOURCE).order_by(Transaction.booked_at.desc())).all()
    out = []
    for p in rows:
        a = (p.details or {}).get("avance")
        if not a:
            continue
        settled_by = db.get(Transaction, a["settled_by"]) if a.get("settled_by") else None
        out.append({
            "id": p.id, "date": p.booked_at, "label": p.merchant.name if p.merchant else p.raw_label.split(" | ")[0][:80],
            "person": a.get("person"), "amount_cents": -p.amount_cents, "settled": bool(a.get("settled")), "settled_on": a.get("settled_on"),
            "settled_label": (settled_by.raw_label.split(" | ")[0][:80] if settled_by else None), "parent_id": (p.details or {}).get("part_de"),
        })
    return out


@router.post("/advances/{part_id}/settle")
def settle_advance(part_id: int, body: SettleIn, db: Session = Depends(get_db)) -> dict:
    p = _get(db, part_id)
    a = (p.details or {}).get("avance")
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ce n'est pas une avance")
    if body.transaction_id is not None:
        r = _get(db, body.transaction_id)
        if r.amount_cents <= 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choisis l'argent reçu (une entrée)")
        r.counted = False  # un remboursement n'est pas un revenu
        r.details = {**(r.details or {}), "remboursement_de": p.id}
    p.details = {**p.details, "avance": {**a, "settled": True, "settled_by": body.transaction_id, "settled_on": date.today().isoformat()}}
    db.commit()
    return {"ok": True}


@router.post("/advances/{part_id}/unsettle")
def unsettle_advance(part_id: int, db: Session = Depends(get_db)) -> dict:
    p = _get(db, part_id)
    a = (p.details or {}).get("avance")
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ce n'est pas une avance")
    if a.get("settled_by"):
        _release_refund(db, a["settled_by"])
    p.details = {**p.details, "avance": {**a, "settled": False, "settled_by": None, "settled_on": None}}
    db.commit()
    return {"ok": True}
