"""Projets par étiquette, contrats, comparaison d'une année sur l'autre, patrimoine."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Account, Contract, Project, RecurringSeries, Tag
from app.security import require_auth
from app.services import projects as svc
from app.services import wealth

router = APIRouter(prefix="/api", tags=["projets"], dependencies=[Depends(require_auth)])


def _today() -> date:
    return date.today()


# --- Projets --------------------------------------------------------------------------------------


class ProjectIn(BaseModel):
    tag_id: int | None = None
    name: str | None = Field(default=None, max_length=50)  # nouvelle étiquette (ou existante du même nom)
    budget_cents: int | None = Field(default=None, gt=0)
    start_date: date | None = None
    end_date: date | None = None
    note: str | None = Field(default=None, max_length=300)


class ProjectPatch(BaseModel):
    budget_cents: int | None = Field(default=None, ge=0)  # 0 : plus de budget
    start_date: date | None = None
    end_date: date | None = None
    clear_dates: bool = False
    note: str | None = Field(default=None, max_length=300)
    archived: bool | None = None


def _check_dates(start: date | None, end: date | None) -> None:
    if start and end and end < start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La date de fin doit suivre la date de début")


@router.get("/projects")
def list_projects(archived: bool = False, db: Session = Depends(get_db)) -> list[dict]:
    return svc.projects_list(db, _today(), archived)


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectIn, db: Session = Depends(get_db)) -> dict:
    _check_dates(body.start_date, body.end_date)
    if body.tag_id is not None:
        tag = db.get(Tag, body.tag_id)
        if tag is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Étiquette inconnue")
    elif body.name and body.name.strip():
        name = body.name.strip()
        tag = db.scalar(select(Tag).where(Tag.name == name)) or Tag(name=name)
        db.add(tag)
        db.flush()
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choisis une étiquette ou donne un nom au projet")
    if db.scalar(select(Project).where(Project.tag_id == tag.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette étiquette est déjà suivie comme projet")
    p = Project(tag_id=tag.id, budget_cents=body.budget_cents, start_date=body.start_date, end_date=body.end_date, note=body.note)
    p.tag = tag
    db.add(p)
    db.commit()
    return svc.project_view(db, p, _today())


def _project(db: Session, project_id: int) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Projet introuvable")
    return p


@router.patch("/projects/{project_id}")
def update_project(project_id: int, body: ProjectPatch, db: Session = Depends(get_db)) -> dict:
    p = _project(db, project_id)
    data = body.model_dump(exclude_unset=True)
    if "budget_cents" in data:
        p.budget_cents = body.budget_cents or None
    if body.clear_dates:
        p.start_date = p.end_date = None
    if "start_date" in data:
        p.start_date = body.start_date
    if "end_date" in data:
        p.end_date = body.end_date
    _check_dates(p.start_date, p.end_date)
    if "note" in data:
        p.note = body.note
    if body.archived is not None:
        p.archived = body.archived
    db.commit()
    return svc.project_view(db, p, _today())


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)) -> dict:
    """Le suivi s'arrête ; l'étiquette et les opérations restent."""
    db.delete(_project(db, project_id))
    db.commit()
    return {"ok": True}


# --- Contrats -------------------------------------------------------------------------------------


class ContractIn(BaseModel):
    label: str | None = Field(default=None, max_length=150)
    recurring_id: int | None = None
    renewal_date: date
    notice_days: int = Field(default=30, ge=0, le=365)
    renew_months: int | None = Field(default=12, ge=1, le=120)  # null : pas de reconduction tacite
    amount_cents: int | None = None
    note: str | None = Field(default=None, max_length=300)


class ContractPatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=150)
    renewal_date: date | None = None
    notice_days: int | None = Field(default=None, ge=0, le=365)
    renew_months: int | None = Field(default=None, ge=0, le=120)  # 0 : pas de reconduction tacite
    amount_cents: int | None = None
    clear_amount: bool = False
    note: str | None = Field(default=None, max_length=300)


@router.get("/contracts")
def list_contracts(db: Session = Depends(get_db)) -> list[dict]:
    out = svc.contracts_list(db, _today())
    db.commit()  # reconductions tacites enregistrées
    return out


@router.post("/contracts", status_code=status.HTTP_201_CREATED)
def create_contract(body: ContractIn, db: Session = Depends(get_db)) -> dict:
    series = None
    if body.recurring_id is not None:
        series = db.get(RecurringSeries, body.recurring_id)
        if series is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Récurrent inconnu")
    label = (body.label or "").strip() or (series.label if series else "")
    if not label:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Donne un nom au contrat")
    c = Contract(label=label[:150], recurring_id=body.recurring_id, renewal_date=body.renewal_date, notice_days=body.notice_days,
                 renew_months=body.renew_months, amount_cents=body.amount_cents, note=body.note)
    db.add(c)
    db.flush()
    db.refresh(c)
    db.commit()
    return svc.contract_view(c, _today())


def _contract(db: Session, contract_id: int) -> Contract:
    c = db.get(Contract, contract_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contrat introuvable")
    return c


@router.patch("/contracts/{contract_id}")
def update_contract(contract_id: int, body: ContractPatch, db: Session = Depends(get_db)) -> dict:
    c = _contract(db, contract_id)
    data = body.model_dump(exclude_unset=True)
    if body.label:
        c.label = body.label.strip()
    if body.renewal_date:
        c.renewal_date = body.renewal_date
    if body.notice_days is not None:
        c.notice_days = body.notice_days
    if "renew_months" in data:
        c.renew_months = body.renew_months or None
    if body.clear_amount:
        c.amount_cents = None
    elif body.amount_cents is not None:
        c.amount_cents = body.amount_cents
    if "note" in data:
        c.note = body.note
    db.commit()
    return svc.contract_view(c, _today())


@router.delete("/contracts/{contract_id}")
def delete_contract(contract_id: int, db: Session = Depends(get_db)) -> dict:
    db.delete(_contract(db, contract_id))
    db.commit()
    return {"ok": True}


# --- Comparaison ----------------------------------------------------------------------------------


@router.get("/compare")
def compare(mode: str = Query(default="ytd", pattern="^(ytd|rolling)$"), db: Session = Depends(get_db)) -> dict:
    """Année civile à date (ytd) ou 12 derniers mois (rolling), contre la même période un an plus tôt."""
    return svc.compare(db, _today(), mode)


# --- Patrimoine -----------------------------------------------------------------------------------


@router.get("/patrimoine")
def patrimoine(db: Session = Depends(get_db)) -> dict:
    out = wealth.overview(db, _today())
    db.commit()  # valeurs du jour des biens et crédits enregistrées
    return out


class ParamsIn(BaseModel):
    purchase_cents: int | None = Field(default=None, gt=0)
    purchase_date: date | None = None
    depreciation_pct: float | None = Field(default=None, ge=0, le=100)
    principal_cents: int | None = Field(default=None, gt=0)
    rate_pct: float | None = Field(default=None, ge=0, le=30)
    months: int | None = Field(default=None, ge=1, le=600)
    first_payment: date | None = None
    insurance_cents: int | None = Field(default=None, ge=0)
    ceiling_cents: int | None = Field(default=None, gt=0)


@router.put("/accounts/{account_id}/params")
def set_params(account_id: int, body: ParamsIn, db: Session = Depends(get_db)) -> dict:
    acc = db.get(Account, account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte introuvable")
    if acc.type not in wealth.PARAM_KEYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Réglages possibles pour un bien, un crédit ou un compte d'épargne")
    acc.params = wealth.clean_params(acc.type, body.model_dump(mode="json"))
    db.flush()
    wealth.refresh_valuations(db, _today())
    db.commit()
    return {"params": acc.params}
