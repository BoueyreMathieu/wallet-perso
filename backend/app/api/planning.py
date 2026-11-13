"""Récurrents (abonnements, prélèvements, salaires…), budgets mensuels et prévision de trésorerie."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Account, Budget, Category, Merchant, RecurringSeries, Transaction
from app.recurrence import next_after
from app.security import require_auth
from app.services import planning
from app.services import recurring as rec

router = APIRouter(prefix="/api", tags=["prévoir"], dependencies=[Depends(require_auth)])

Frequency = Literal["hebdomadaire", "mensuel", "bimestriel", "trimestriel", "semestriel", "annuel"]
Status = Literal["suggere", "actif", "ignore", "termine"]


# --- Récurrents ---------------------------------------------------------------------------------


class RecurringOut(BaseModel):
    id: int
    label: str
    merchant_id: int | None
    merchant: str | None
    account_id: int | None
    account_name: str | None
    category_id: int | None
    amount_cents: int
    frequency: str
    frequency_label: str
    monthly_cents: int
    yearly_cents: int
    next_date: date | None
    last_date: date | None
    first_date: date | None
    end_date: date | None = None
    occurrences: int
    total_cents: int
    status: str
    source: str
    basis: str = "vendeur"
    kind: str
    late_days: int
    maybe_ended: bool
    previous_amount_cents: int | None
    price_changed_on: date | None
    price_increase: bool


class RecurringSummary(BaseModel):
    items: list[RecurringOut]
    to_confirm: int
    monthly_out_cents: int  # dépenses récurrentes (hors virements), équivalent mensuel
    monthly_in_cents: int  # revenus récurrents
    yearly_out_cents: int


class RecurringIn(BaseModel):
    label: str = Field(min_length=1, max_length=150)
    account_id: int
    amount_cents: int  # signé : négatif = sortie
    frequency: Frequency
    next_date: date
    category_id: int | None = None
    merchant_id: int | None = None
    end_date: date | None = None


class RecurringPatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=150)
    status: Status | None = None
    amount_cents: int | None = None
    frequency: Frequency | None = None
    next_date: date | None = None
    category_id: int | None = None
    end_date: date | None = None  # null = sans fin


class FromTransactionIn(BaseModel):
    frequency: Frequency = "mensuel"


class LinkedTransaction(BaseModel):
    id: int
    booked_at: date
    amount_cents: int
    label: str


def _today() -> date:
    return date.today()


def _out(db: Session, items: list[RecurringSeries]) -> list[RecurringOut]:
    totals = dict(
        db.execute(
            select(Transaction.recurring_id, func.sum(Transaction.amount_cents))
            .where(Transaction.recurring_id.in_([s.id for s in items]))
            .group_by(Transaction.recurring_id)
        ).all()
    ) if items else {}
    accounts = dict(db.execute(select(Account.id, Account.name)).all())
    today = _today()
    return [RecurringOut(**rec.describe(db, s, today, {k: int(v) for k, v in totals.items()}, accounts)) for s in items]


def _get(db: Session, series_id: int) -> RecurringSeries:
    s = db.get(RecurringSeries, series_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Récurrent introuvable")
    return s


@router.get("/recurring", response_model=RecurringSummary)
def list_recurring(all: bool = False, db: Session = Depends(get_db)):
    q = select(RecurringSeries).options(selectinload(RecurringSeries.merchant))
    if not all:
        q = q.where(RecurringSeries.status.in_(rec.ACTIVE_STATUSES))
    items = _out(db, db.scalars(q).all())
    order = {"suggere": 0, "actif": 1, "termine": 2, "ignore": 3}
    items.sort(key=lambda i: (order.get(i.status, 9), i.next_date or date.max, i.amount_cents))
    live = [i for i in items if i.status in rec.ACTIVE_STATUSES and not i.maybe_ended]
    out_m = -sum(i.monthly_cents for i in live if i.kind == "depense")
    return RecurringSummary(
        items=items,
        to_confirm=sum(1 for i in items if i.status == "suggere"),
        monthly_out_cents=out_m,
        monthly_in_cents=sum(i.monthly_cents for i in live if i.kind == "revenu"),
        yearly_out_cents=out_m * 12,
    )


@router.post("/recurring/refresh")
def refresh_recurring(db: Session = Depends(get_db)) -> dict:
    res = rec.refresh(db, _today())
    db.commit()
    return res


@router.post("/recurring", response_model=RecurringOut, status_code=status.HTTP_201_CREATED)
def create_recurring(body: RecurringIn, db: Session = Depends(get_db)):
    if db.get(Account, body.account_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Compte inconnu")
    if body.category_id is not None and db.get(Category, body.category_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Catégorie inconnue")
    if body.merchant_id is not None and db.get(Merchant, body.merchant_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Vendeur inconnu")
    if body.amount_cents == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Montant attendu non nul")
    if body.end_date is not None and body.end_date < body.next_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La date de fin doit suivre la prochaine échéance")
    s = RecurringSeries(
        label=body.label.strip(), account_id=body.account_id, expected_amount_cents=body.amount_cents,
        frequency=body.frequency, next_expected_date=body.next_date, category_id=body.category_id,
        merchant_id=body.merchant_id, source="manuel", status="actif", end_date=body.end_date,
    )
    db.add(s)
    db.commit()
    return _out(db, [s])[0]


@router.post("/recurring/from-transaction/{tx_id}", response_model=RecurringOut, status_code=status.HTTP_201_CREATED)
def recurring_from_transaction(tx_id: int, body: FromTransactionIn, db: Session = Depends(get_db)):
    """« Suivre comme récurrent » depuis une opération : même vendeur, compte, montant ; prochaine échéance calculée."""
    t = db.get(Transaction, tx_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opération introuvable")
    if t.recurring_id is not None:
        s = _get(db, t.recurring_id)
        s.status = "actif"
        s.frequency = body.frequency
        db.commit()
        return _out(db, [s])[0]
    label = t.merchant.name if t.merchant else t.raw_label.split(" | ")[0][:150]
    s = RecurringSeries(
        label=label, account_id=t.account_id, merchant_id=t.merchant_id, category_id=t.category_id,
        expected_amount_cents=t.amount_cents, frequency=body.frequency, source="manuel", status="actif",
        is_transfer=t.is_transfer, first_date=t.booked_at, last_date=t.booked_at, occurrences=1,
        next_expected_date=next_after(t.booked_at, body.frequency),
    )
    db.add(s)
    db.flush()
    t.recurring_id = s.id
    db.commit()
    return _out(db, [s])[0]


@router.patch("/recurring/{series_id}", response_model=RecurringOut)
def update_recurring(series_id: int, body: RecurringPatch, db: Session = Depends(get_db)):
    s = _get(db, series_id)
    data = body.model_dump(exclude_unset=True)
    if "category_id" in data and data["category_id"] is not None and db.get(Category, data["category_id"]) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Catégorie inconnue")
    if "label" in data:
        s.label = data["label"].strip()
    if "status" in data:
        s.status = data["status"]
        if data["status"] == "ignore":
            # Refusée : ses opérations ne sont plus marquées récurrentes.
            db.query(Transaction).filter(Transaction.recurring_id == s.id).update({"recurring_id": None})
    if data.get("amount_cents") is not None:
        s.expected_amount_cents = data["amount_cents"]
    if data.get("frequency"):
        s.frequency = data["frequency"]
        if s.last_date and "next_date" not in data:
            s.next_expected_date = next_after(s.last_date, s.frequency)
    if data.get("next_date"):
        s.next_expected_date = data["next_date"]
    if "category_id" in data:
        s.category_id = data["category_id"]
    if "end_date" in data:
        s.end_date = data["end_date"]
        if s.end_date is not None and s.end_date < date.today() and s.status in ("actif", "suggere"):
            s.status = "termine"
        elif s.end_date is None or s.end_date >= date.today():
            if s.status == "termine" and "status" not in data:
                s.status = "actif"  # fin repoussée ou retirée : la série reprend
    db.commit()
    return _out(db, [s])[0]


@router.delete("/recurring/{series_id}")
def delete_recurring(series_id: int, db: Session = Depends(get_db)) -> dict:
    """Déclarée à la main : supprimée. Détectée : « ignorée » (elle ne sera plus proposée)."""
    s = _get(db, series_id)
    db.query(Transaction).filter(Transaction.recurring_id == s.id).update({"recurring_id": None})
    if s.source == "manuel":
        db.delete(s)
    else:
        s.status = "ignore"
    db.commit()
    return {"ok": True}


@router.get("/recurring/{series_id}/transactions", response_model=list[LinkedTransaction])
def recurring_transactions(series_id: int, db: Session = Depends(get_db)):
    _get(db, series_id)
    rows = db.scalars(
        select(Transaction).options(selectinload(Transaction.merchant))
        .where(Transaction.recurring_id == series_id).order_by(Transaction.booked_at.desc()).limit(60)
    ).all()
    return [LinkedTransaction(id=t.id, booked_at=t.booked_at, amount_cents=t.amount_cents, label=t.raw_label.split(" | ")[0][:80]) for t in rows]


# --- Budgets ------------------------------------------------------------------------------------


class BudgetIn(BaseModel):
    monthly_amount_cents: int = Field(gt=0)
    alert_threshold_pct: int = Field(default=80, ge=10, le=100)


def _month(month: str | None) -> date:
    if not month:
        return _today()
    try:
        y, m = (int(x) for x in month.split("-"))
        return date(y, m, 1)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Mois attendu au format AAAA-MM") from e


@router.get("/budgets")
def get_budgets(month: str | None = None, db: Session = Depends(get_db)) -> dict:
    return planning.budgets_overview(db, _month(month), _today())


class GlobalBudgetIn(BaseModel):
    monthly_amount_cents: int | None = Field(default=None, gt=0)  # null : pas de budget global


@router.put("/budgets/global")
def set_global_budget(body: GlobalBudgetIn, db: Session = Depends(get_db)) -> dict:
    """Budget sur l'ensemble des dépenses du mois (en plus, ou à la place, des budgets par catégorie)."""
    from app.seed import set_meta

    set_meta(db, "global_budget_cents", str(body.monthly_amount_cents) if body.monthly_amount_cents else "")
    db.commit()
    return {"monthly_amount_cents": body.monthly_amount_cents}


@router.put("/budgets/{category_id}")
def set_budget(category_id: int, body: BudgetIn, db: Session = Depends(get_db)) -> dict:
    cat = db.get(Category, category_id)
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Catégorie introuvable")
    if cat.kind != "depense":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Un budget se fixe sur une catégorie de dépenses")
    b = db.scalar(select(Budget).where(Budget.category_id == category_id))
    if b is None:
        b = Budget(category_id=category_id, monthly_amount_cents=body.monthly_amount_cents)
        db.add(b)
    b.monthly_amount_cents = body.monthly_amount_cents
    b.alert_threshold_pct = body.alert_threshold_pct
    db.commit()
    return {"ok": True}


@router.delete("/budgets/{category_id}")
def delete_budget(category_id: int, db: Session = Depends(get_db)) -> dict:
    b = db.scalar(select(Budget).where(Budget.category_id == category_id))
    if b is not None:
        db.delete(b)
        db.commit()
    return {"ok": True}


# --- Prévision de trésorerie --------------------------------------------------------------------


class ScenarioIn(BaseModel):
    """Scénario « et si… » : plaisirs à X %, budgets appliqués, objectifs par catégorie, épargne en plus."""

    plaisir_pct: int = Field(default=100, ge=0, le=200)
    apply_budgets: bool = False
    targets: dict[int, int] = Field(default_factory=dict)  # {id de catégorie: objectif mensuel en centimes}
    extra_saving_cents: int = Field(default=0, ge=0, le=10_000_000)

    def to_scenario(self) -> planning.Scenario:
        return planning.Scenario(
            plaisir_pct=self.plaisir_pct, apply_budgets=self.apply_budgets,
            targets={int(k): max(int(v), 0) for k, v in self.targets.items()}, extra_saving_cents=self.extra_saving_cents,
        )


def _ids(accounts: str | None) -> list[int] | None:
    return [int(x) for x in accounts.split(",") if x.strip().isdigit()] if accounts else None


def _horizon(today: date, horizon: str, end_date: date | None) -> date:
    """Fin de la période : une date choisie, fin_du_mois, fin_mois_prochain, ou un nombre de jours (≤ 3 ans)."""
    limit = today + timedelta(days=3 * 366)
    if end_date is not None:
        if end_date <= today:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choisis une date dans le futur")
        return min(end_date, limit)
    if horizon == "fin_du_mois":
        end = planning.month_bounds(today)[1]
        if (end - today).days < 3:  # dernier(s) jour(s) du mois : on montre aussi le mois suivant
            end = planning.month_bounds(end + timedelta(days=1))[1]
        return end
    if horizon == "fin_mois_prochain":
        return planning.month_bounds(planning.month_bounds(today)[1] + timedelta(days=1))[1]
    try:
        return min(today + timedelta(days=max(int(horizon), 7)), limit)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Horizon : fin_du_mois, fin_mois_prochain, un nombre de jours ou une date") from e


@router.get("/forecast")
def get_forecast(
    horizon: str = Query(default="fin_du_mois", description="fin_du_mois, fin_mois_prochain ou un nombre de jours"),
    end_date: date | None = Query(default=None, description="ou une date de fin (AAAA-MM-JJ)"),
    accounts: str | None = Query(default=None, description="ids de comptes séparés par des virgules"),
    db: Session = Depends(get_db),
) -> dict:
    today = _today()
    return planning.forecast(db, today, _horizon(today, horizon, end_date), _ids(accounts))


@router.post("/forecast")
def post_forecast(
    body: ScenarioIn,
    horizon: str = Query(default="fin_du_mois"),
    end_date: date | None = Query(default=None),
    accounts: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Même chose, avec un scénario."""
    today = _today()
    return planning.forecast(db, today, _horizon(today, horizon, end_date), _ids(accounts), body.to_scenario())


def _months(today: date, months: int, until: str | None) -> int:
    if not until:
        return months
    try:
        y, m = (int(x) for x in until.split("-"))
        n = (y - today.year) * 12 + (m - today.month) + 1
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Mois attendu au format AAAA-MM") from e
    if n < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choisis un mois après le mois prochain")
    return min(n, 36)


@router.get("/projection")
def get_projection(
    months: int = Query(default=12, ge=2, le=36),
    until: str | None = Query(default=None, description="ou jusqu'à un mois (AAAA-MM)"),
    accounts: str | None = Query(default=None),
    plaisir_pct: int = Query(default=100, ge=0, le=200),
    extra_saving_cents: int = Query(default=0, ge=0, le=10_000_000),
    db: Session = Depends(get_db),
) -> dict:
    today = _today()
    sc = planning.Scenario(plaisir_pct=plaisir_pct, extra_saving_cents=extra_saving_cents)
    return planning.projection(db, today, _months(today, months, until), _ids(accounts), sc)


@router.post("/projection")
def post_projection(
    body: ScenarioIn,
    months: int = Query(default=12, ge=2, le=36),
    until: str | None = Query(default=None),
    accounts: str | None = Query(default=None),
    rate: float = Query(default=2.0, ge=0, le=15, description="rendement annuel de l'épargne (%) pour le patrimoine prévu"),
    db: Session = Depends(get_db),
) -> dict:
    today = _today()
    return planning.projection(db, today, _months(today, months, until), _ids(accounts), body.to_scenario(), rate=rate)


def recurring_alerts(db: Session, today: date) -> dict:
    """Pour l'accueil : récurrents à confirmer, hausses de prix récentes."""
    active = db.scalars(select(RecurringSeries).where(RecurringSeries.status.in_(rec.ACTIVE_STATUSES))).all()
    hikes = [
        s.label for s in active
        if s.previous_amount_cents is not None and s.price_changed_on and (today - s.price_changed_on).days <= 45
        and abs(s.expected_amount_cents) > abs(s.previous_amount_cents) and s.expected_amount_cents < 0
    ]
    return {"to_confirm": sum(1 for s in active if s.status == "suggere"), "price_increases": hikes}

