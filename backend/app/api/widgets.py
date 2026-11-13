"""Résumé pour les widgets Android : un seul appel, peu de données.

Chaque widget du téléphone pioche ce dont il a besoin dans ce résumé (solde d'un compte, fin du mois prévue,
dépenses du mois par couche, budgets, prochaines échéances, patrimoine, dernières opérations).
Les blocs « calculés » (prévision, budgets, échéances…) sont protégés : si l'un d'eux échoue, il vaut null / vide
et les autres widgets continuent de s'afficher.
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.dashboard import _label, dashboard
from app.db import get_db
from app.layers import NATURES
from app.models import Account, Budget, Category, PendingTransaction, RecurringSeries, Transaction
from app.recurrence import occurrences
from app.security import require_auth
from app.services import planning
from app.services.balances import current_balance
from app.services.recurring import ACTIVE_STATUSES

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/widgets", tags=["widgets"], dependencies=[Depends(require_auth)])

RECENT_PER_ACCOUNT = 5
UPCOMING_DAYS = 31


class WidgetTx(BaseModel):
    booked_at: date
    label: str
    amount_cents: int
    account_name: str


class WidgetAccount(BaseModel):
    id: int | None = None
    name: str
    type: str
    institution: str | None = None
    balance_cents: int | None
    balance_date: date | None = None
    in_net_worth: bool = True
    month_in_cents: int = 0  # entrées du mois sur ce compte (virements compris)
    month_out_cents: int = 0  # sorties du mois (positif)
    pending_cents: int = 0  # opérations « à venir » pas encore comptabilisées
    recent: list[WidgetTx] = []


class WidgetEndOfMonth(BaseModel):
    horizon: date
    start_cents: int
    balance_cents: int  # solde prévu à l'horizon
    low_cents: int
    low_date: date
    points: list[int]  # solde prévu jour par jour, d'aujourd'hui à l'horizon
    accounts: list[str]


class WidgetCategory(BaseModel):
    name: str
    icon: str | None = None
    spent_cents: int
    prev_spent_cents: int


class WidgetBudget(BaseModel):
    name: str
    icon: str | None = None
    budget_cents: int
    spent_cents: int
    projected_cents: int
    level: str  # ok | alerte | depasse


class WidgetEvent(BaseModel):
    date: date
    label: str
    amount_cents: int
    kind: str  # depense | revenu
    account_name: str | None = None


class WidgetSummary(BaseModel):
    version: int = 2
    month: str
    spent_cents: int
    prev_spent_same_day_cents: int
    prev_spent_cents: int
    income_cents: int
    daily_cumulative: list[int]
    prev_daily_cumulative: list[int]
    net_worth_cents: int
    net_worth_change_cents: int = 0  # mouvements du mois sur les comptes du patrimoine
    accounts: list[WidgetAccount]
    recent: list[WidgetTx]
    to_categorize: int
    pending_spent_cents: int = 0
    layers: dict[str, int] = {}  # dépensé ce mois : fixe / essentiel / plaisir
    top_categories: list[WidgetCategory] = []
    budgets: list[WidgetBudget] = []
    end_of_month: WidgetEndOfMonth | None = None
    upcoming: list[WidgetEvent] = []
    generated_at: datetime


def _safe(what: str, fn, default):
    try:
        return fn()
    except Exception:  # un bloc en échec ne doit pas priver les autres widgets de données
        log.exception("Widgets : calcul « %s » en échec", what)
        return default


def _horizon(today: date) -> date:
    """Fin du mois ; les tout derniers jours du mois, fin du mois suivant (comme l'onglet Trésorerie)."""
    end = planning.month_bounds(today)[1]
    if (end - today).days < 3:
        end = planning.month_bounds(end + timedelta(days=1))[1]
    return end


def _end_of_month(db: Session, today: date) -> WidgetEndOfMonth:
    f = planning.forecast(db, today, _horizon(today))
    return WidgetEndOfMonth(
        horizon=f["horizon"],
        start_cents=f["start_balance_cents"],
        balance_cents=f["end_balance_cents"],
        low_cents=f["lowest"]["balance_cents"],
        low_date=f["lowest"]["date"],
        points=[p["balance_cents"] for p in f["points"]],
        accounts=[a for a in f["accounts"] if a],
    )


def _layers(db: Session, today: date) -> dict[str, int]:
    start = today.replace(day=1)
    natures = planning.category_natures(db)
    rows = db.execute(
        select(Transaction.amount_cents, Transaction.category_id, Transaction.recurring_id).where(
            Transaction.booked_at >= start,
            Transaction.booked_at <= today,
            Transaction.counted.is_(True),
            Transaction.is_transfer.is_(False),
            Transaction.amount_cents < 0,
        )
    ).all()
    totals = {n: 0 for n in NATURES}
    for r in rows:
        layer = planning.layer_of(r.category_id, r.recurring_id, natures)
        totals[layer if layer in totals else "essentiel"] -= r.amount_cents
    return totals


def _categories(db: Session) -> dict[int, Category]:
    return {c.id: c for c in db.scalars(select(Category))}


def _top_categories(by_category, cats: dict[int, Category]) -> list[WidgetCategory]:
    out = []
    for c in by_category:
        if c.spent_cents <= 0:
            continue
        cat = cats.get(c.category_id) if c.category_id is not None else None
        out.append(WidgetCategory(
            name=cat.name if cat else "À catégoriser",
            icon=cat.icon if cat else "❓",
            spent_cents=c.spent_cents,
            prev_spent_cents=c.prev_spent_cents,
        ))
    return out[:6]


def _budgets(db: Session, today: date, cats: dict[int, Category]) -> list[WidgetBudget]:
    if not db.scalar(select(func.count()).select_from(Budget)):
        return []
    overview = planning.budgets_overview(db, today, today)
    return [
        WidgetBudget(
            name=cats[i["category_id"]].name if i["category_id"] in cats else "?",
            icon=cats[i["category_id"]].icon if i["category_id"] in cats else None,
            budget_cents=i["budget_cents"],
            spent_cents=i["spent_cents"],
            projected_cents=i["projected_cents"],
            level=i["level"],
        )
        for i in overview["items"]
    ]


def _upcoming(db: Session, today: date, names: dict[int, str]) -> list[WidgetEvent]:
    """Récurrents attendus (hors virements entre comptes) d'aujourd'hui à dans un mois."""
    hi = today + timedelta(days=UPCOMING_DAYS)
    events = []
    series = db.scalars(select(RecurringSeries).where(RecurringSeries.status.in_(ACTIVE_STATUSES))).all()
    for s in series:
        if s.is_transfer or not s.expected_amount_cents:
            continue
        for d in occurrences(s.next_expected_date, s.frequency, today, min(hi, s.end_date or hi)):  # date de fin respectée
            events.append(WidgetEvent(
                date=d, label=s.label, amount_cents=s.expected_amount_cents,
                kind="revenu" if s.expected_amount_cents > 0 else "depense",
                account_name=names.get(s.account_id) if s.account_id else None,
            ))
    events.sort(key=lambda e: (e.date, e.amount_cents))
    return events[:20]


def _tx(t: Transaction) -> WidgetTx:
    return WidgetTx(booked_at=t.booked_at, label=_label(t), amount_cents=t.amount_cents, account_name=t.account.name)


@router.get("/summary", response_model=WidgetSummary)
def summary(db: Session = Depends(get_db)):
    today = date.today()
    month_start = today.replace(day=1)
    d = dashboard(month=None, date_from=None, date_to=None, accounts=None, category_id=None, db=db)

    # Mouvements du mois et opérations « à venir », par compte.
    flows: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for account_id, amount in db.execute(
        select(Transaction.account_id, Transaction.amount_cents).where(Transaction.booked_at >= month_start)
    ).all():
        flows[account_id][0 if amount > 0 else 1] += amount
    pending: dict[int, int] = defaultdict(int)
    for account_id, amount in db.execute(select(PendingTransaction.account_id, PendingTransaction.amount_cents)).all():
        pending[account_id] += amount

    accounts = []
    net = 0
    net_change = 0
    names: dict[int, str] = {}
    for a in db.scalars(select(Account).where(Account.is_archived.is_(False)).order_by(Account.name)):
        names[a.id] = a.name
        bal, bal_date = current_balance(db, a.id)
        month_in, month_out = flows[a.id]
        if a.include_in_net_worth:
            net += bal or 0
            net_change += month_in + month_out
        recent = db.scalars(
            select(Transaction)
            .options(selectinload(Transaction.merchant), selectinload(Transaction.account))
            .where(Transaction.account_id == a.id)
            .order_by(Transaction.booked_at.desc(), Transaction.id.desc())
            .limit(RECENT_PER_ACCOUNT)
        ).all()
        accounts.append(WidgetAccount(
            id=a.id, name=a.name, type=a.type, institution=a.institution, balance_cents=bal, balance_date=bal_date,
            in_net_worth=a.include_in_net_worth, month_in_cents=month_in, month_out_cents=-month_out,
            pending_cents=pending[a.id], recent=[_tx(t) for t in recent],
        ))
    accounts.sort(key=lambda a: -(a.balance_cents or 0))

    recent = db.scalars(
        select(Transaction)
        .options(selectinload(Transaction.merchant), selectinload(Transaction.account))
        .order_by(Transaction.booked_at.desc(), Transaction.id.desc())
        .limit(8)
    ).all()
    cats = _categories(db)
    return WidgetSummary(
        month=d.month,
        spent_cents=d.spent_cents,
        prev_spent_same_day_cents=d.prev_spent_same_day_cents,
        prev_spent_cents=d.prev_spent_cents,
        income_cents=d.income_cents,
        daily_cumulative=d.daily_cumulative,
        prev_daily_cumulative=d.prev_daily_cumulative,
        net_worth_cents=net,
        net_worth_change_cents=net_change,
        accounts=accounts,
        recent=[_tx(t) for t in recent],
        to_categorize=d.todo.to_categorize_ops,
        pending_spent_cents=d.pending_spent_cents,
        layers=_safe("couches", lambda: _layers(db, today), {}),
        top_categories=_safe("catégories", lambda: _top_categories(d.by_category, cats), []),
        budgets=_safe("budgets", lambda: _budgets(db, today, cats), []),
        end_of_month=_safe("fin du mois", lambda: _end_of_month(db, today), None),
        upcoming=_safe("échéances", lambda: _upcoming(db, today, names), []),
        generated_at=datetime.now(timezone.utc),
    )
