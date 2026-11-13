"""Objectifs d'épargne : où j'en suis, combien mettre de côté chaque mois, quand je l'atteindrai à ce rythme.

- Objectif rattaché à un compte (livret…) : le solde du compte est réparti entre ses objectifs par priorité
  (le 1er servi d'abord). Le rythme = ce qui est arrivé en moyenne sur ce compte ces 3 derniers mois.
- Objectif sans compte : montant mis de côté tenu à la main.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, Goal, Transaction
from app.services.balances import current_balance


def _add_months(d: date, n: int) -> date:
    idx = d.year * 12 + d.month - 1 + n
    y, m = idx // 12, idx % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def months_between(a: date, b: date) -> int:
    """Mois entiers (au moins 1) de a à b."""
    return max(1, (b.year - a.year) * 12 + b.month - a.month + (1 if b.day >= a.day else 0))


def _monthly_inflow(db: Session, account_id: int, today: date) -> int:
    """Arrivées nettes moyennes sur le compte ces 3 derniers mois complets."""
    first = today.replace(day=1)
    lo = _add_months(first, -3)
    total = db.scalar(select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
        Transaction.account_id == account_id, Transaction.booked_at >= lo, Transaction.booked_at < first, Transaction.counted.is_(True),
    )) or 0
    return round(total / 3)


def goals_view(db: Session, today: date) -> list[dict]:
    goals = db.scalars(select(Goal).order_by(Goal.priority, Goal.id)).all()
    accounts = {a.id: a for a in db.scalars(select(Account))}
    left: dict[int, int] = {}
    inflow: dict[int, int] = {}
    future_used: dict[int, int] = defaultdict(int)  # mois d'arrivées déjà « promis » aux objectifs prioritaires
    out = []
    for g in goals:
        if g.account_id is not None and g.account_id in accounts:
            if g.account_id not in left:
                left[g.account_id] = max(current_balance(db, g.account_id)[0] or 0, 0)
                inflow[g.account_id] = _monthly_inflow(db, g.account_id, today)
            current = min(left[g.account_id], g.target_cents)
            left[g.account_id] -= current
            rate = inflow[g.account_id]
        else:
            current, rate = min(g.saved_cents, g.target_cents), None
        remaining = max(g.target_cents - current, 0)
        needed = None
        if g.target_date and remaining > 0:
            needed = -(-remaining // months_between(today, g.target_date)) if g.target_date > today else remaining
        eta = None
        if remaining == 0:
            eta = today
        elif rate and rate > 0 and g.account_id is not None:
            months = -(-remaining // rate) + future_used[g.account_id]
            future_used[g.account_id] = months
            eta = _add_months(today, months)
        status = "atteint" if remaining == 0 else (
            "en_avance" if eta and g.target_date and eta <= g.target_date else
            "en_retard" if g.target_date and (eta is None or eta > g.target_date) else "en_cours"
        )
        out.append({
            "id": g.id, "name": g.name, "icon": g.icon, "target_cents": g.target_cents, "target_date": g.target_date,
            "account_id": g.account_id, "account_name": accounts[g.account_id].name if g.account_id in accounts else None,
            "priority": g.priority, "saved_cents": g.saved_cents, "current_cents": current, "remaining_cents": remaining,
            "progress": round(current / g.target_cents, 3) if g.target_cents else 1.0, "monthly_needed_cents": needed,
            "monthly_rate_cents": rate, "eta": eta, "status": status,
        })
    return out

