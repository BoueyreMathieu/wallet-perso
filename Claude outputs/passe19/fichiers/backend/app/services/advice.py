"""Conseils : construit le contexte depuis la base (voir app/advice.py pour les règles), retire ceux écartés."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.advice import Advice, CatTrend, Context, FEES_CATEGORIES, Series, SmallSpender, advise
from app.models import Account, Category, Connection, Merchant, RecurringSeries, Transaction
from app.recurrence import FREQUENCIES, grace_days, monthly_cost
from app.seed import get_meta, set_meta
from app.services import planning
from app.services.balances import current_balance
from app.services.recurring import ACTIVE_STATUSES

DISMISSED_KEY = "advice_dismissed"


def _month_start(d: date, back: int) -> date:
    idx = d.year * 12 + d.month - 1 - back
    return date(idx // 12, idx % 12 + 1, 1)


def build_context(db: Session, today: date) -> Context:
    ids = planning.default_accounts(db)
    names = {c.id: c.name for c in db.scalars(select(Category))}
    model = planning.build_model(db, today, ids)
    ctx = Context(today=today)
    ctx.trends = [CatTrend(cid, names.get(cid, "À catégoriser") if cid else "À catégoriser", u.layer, u.monthly, u.history)
                  for cid, u in model.units.items()]

    recurring_monthly = 0
    for s in db.scalars(select(RecurringSeries).where(RecurringSeries.status.in_(ACTIVE_STATUSES))):
        monthly = abs(monthly_cost(s.expected_amount_cents, s.frequency))
        late = (today - s.next_expected_date).days if s.next_expected_date and s.next_expected_date < today else 0
        ctx.series.append(Series(
            s.id, s.label, names.get(s.category_id) if s.category_id else None, s.expected_amount_cents, monthly, s.is_transfer, s.status,
            s.previous_amount_cents, s.price_changed_on, late > grace_days(s.frequency) if s.frequency in FREQUENCIES else False,
        ))
        if s.expected_amount_cents < 0 and not s.is_transfer and s.status in ("actif", "suggere"):
            recurring_monthly += monthly
        if s.status == "suggere":
            ctx.to_confirm += 1
    ctx.monthly_spending = recurring_monthly + sum(u.monthly for u in model.units.values())

    # Petits achats (moins de 15 €) des 30 derniers jours, par vendeur.
    rows = db.execute(
        select(Merchant.name, Transaction.category_id, Transaction.amount_cents).join(Merchant, Transaction.merchant_id == Merchant.id).where(
            Transaction.booked_at > today - timedelta(days=30), Transaction.amount_cents < 0, Transaction.amount_cents > -1500,
            Transaction.counted.is_(True), Transaction.is_transfer.is_(False), Transaction.recurring_id.is_(None),
        )
    ).all()
    small: dict[str, list] = defaultdict(lambda: [None, 0, 0])
    for r in rows:
        e = small[r.name]
        e[0] = e[0] or r.category_id
        e[1] += 1
        e[2] -= r.amount_cents
    ctx.small = [SmallSpender(name, v[0], v[1], v[2]) for name, v in small.items()]

    accounts = db.scalars(select(Account).where(Account.is_archived.is_(False))).all()
    ctx.liquid_balance = sum(current_balance(db, a.id)[0] or 0 for a in accounts if a.id in ids)
    ctx.has_savings_account = any(a.type == "epargne" for a in accounts)

    # Revenus et dépenses des 3 derniers mois complets (comptes du quotidien, hors virements entre mes comptes).
    for back in (3, 2, 1):
        lo, hi = _month_start(today, back), _month_start(today, back - 1) - timedelta(days=1)
        q = select(Transaction.amount_cents).where(
            Transaction.booked_at >= lo, Transaction.booked_at <= hi, Transaction.counted.is_(True), Transaction.is_transfer.is_(False),
        )
        if ids:
            q = q.where(Transaction.account_id.in_(ids))
        amounts = list(db.scalars(q))
        if amounts:
            ctx.income_months.append(sum(a for a in amounts if a > 0))
            ctx.spending_months.append(-sum(a for a in amounts if a < 0))

    fees_ids = [cid for cid, n in names.items() if n in FEES_CATEGORIES]
    if fees_ids:
        ctx.fees_3_months = -(db.scalar(select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.category_id.in_(fees_ids), Transaction.booked_at > today - timedelta(days=91), Transaction.counted.is_(True),
        )) or 0)

    if ids:
        f = planning.forecast(db, today, today + timedelta(days=30), ids)
        if f["lowest"]:
            ctx.lowest_30_days, ctx.lowest_date = f["lowest"]["balance_cents"], f["lowest"]["date"]

    ctx.uncategorized = db.scalar(select(func.count()).select_from(Transaction).where(
        Transaction.category_id.is_(None), Transaction.counted.is_(True), Transaction.is_transfer.is_(False),
        Transaction.booked_at > today - timedelta(days=91),
    )) or 0
    now = datetime.now(timezone.utc)
    for c in db.scalars(select(Connection).where(Connection.status == "actif", Connection.consent_expires_at.is_not(None))):
        exp = c.consent_expires_at if c.consent_expires_at.tzinfo else c.consent_expires_at.replace(tzinfo=timezone.utc)
        ctx.consent_days_left.append((c.label, (exp - now).days))
    return ctx


def _dismissed(db: Session, today: date) -> dict[str, str]:
    try:
        data = json.loads(get_meta(db, DISMISSED_KEY) or "{}")
    except ValueError:
        data = {}
    return {k: v for k, v in data.items() if isinstance(v, str) and v >= today.isoformat()}


def list_advice(db: Session, today: date) -> list[Advice]:
    hidden = _dismissed(db, today)
    return [a for a in advise(build_context(db, today)) if a.id not in hidden]


def dismiss(db: Session, advice_id: str, days: int, today: date) -> None:
    """Écarte un conseil pour `days` jours (il revient ensuite s'il est toujours vrai)."""
    data = _dismissed(db, today)
    data[advice_id[:200]] = (today + timedelta(days=days)).isoformat()
    set_meta(db, DISMISSED_KEY, json.dumps(data))
    db.commit()
