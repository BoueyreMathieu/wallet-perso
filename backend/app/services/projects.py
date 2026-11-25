"""Projets par étiquette, contrats (échéances), comparaison d'une année sur l'autre."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Contract, Project, RecurringSeries, Tag, Transaction
from app.services.services import tag_condition
from app.wealth import _add_months

# --- Projets --------------------------------------------------------------------------------------


def project_view(db: Session, p: Project, today: date) -> dict:
    q = select(Transaction.booked_at, Transaction.amount_cents, Transaction.category_id).where(
        tag_condition(p.tag_id), Transaction.counted.is_(True), Transaction.is_transfer.is_(False)
    )
    if p.start_date:
        q = q.where(Transaction.booked_at >= p.start_date)
    if p.end_date:
        q = q.where(Transaction.booked_at <= p.end_date)
    rows = db.execute(q).all()
    parents = dict(db.execute(select(Category.id, Category.parent_id)).all())
    spent = -sum(a for _, a, _ in rows if a < 0)
    refunds = sum(a for _, a, _ in rows if a > 0)
    net = spent - refunds  # remboursements déduits
    by_cat: dict[int | None, int] = defaultdict(int)
    by_month: dict[str, int] = defaultdict(int)
    for d, a, cid in rows:
        top = parents.get(cid) or cid if cid is not None else None
        by_cat[top] -= a
        by_month[d.strftime("%Y-%m")] -= a
    level = "ok"
    if p.budget_cents:
        if net > p.budget_cents:
            level = "depasse"
        elif net >= 0.8 * p.budget_cents:
            level = "alerte"
    days_left = (p.end_date - today).days if p.end_date and p.end_date >= today else None
    return {
        "id": p.id, "tag_id": p.tag_id, "name": p.tag.name if p.tag else "?", "color": p.tag.color if p.tag else None,
        "budget_cents": p.budget_cents, "start_date": p.start_date, "end_date": p.end_date, "note": p.note, "archived": p.archived,
        "spent_cents": spent, "refunds_cents": refunds, "net_cents": net, "count": len(rows),
        "remaining_cents": (p.budget_cents - net) if p.budget_cents else None, "level": level, "days_left": days_left,
        "first_date": min((d for d, _, _ in rows), default=None), "last_date": max((d for d, _, _ in rows), default=None),
        "by_category": [{"category_id": c, "net_cents": v} for c, v in sorted(by_cat.items(), key=lambda kv: -kv[1]) if v != 0],
        "by_month": [{"month": m, "net_cents": v} for m, v in sorted(by_month.items())],
    }


def projects_list(db: Session, today: date, include_archived: bool = False) -> list[dict]:
    q = select(Project).join(Tag, Tag.id == Project.tag_id)
    if not include_archived:
        q = q.where(Project.archived.is_(False))
    return [project_view(db, p, today) for p in db.scalars(q.order_by(Project.archived, Tag.name))]


# --- Contrats -------------------------------------------------------------------------------------


def roll_renewals(db: Session, today: date) -> int:
    """Reconduction tacite : une échéance passée avance d'une période (12 mois…). Sans reconduction : rien ne bouge."""
    n = 0
    for c in db.scalars(select(Contract).where(Contract.renewal_date < today, Contract.renew_months.is_not(None))):
        while c.renewal_date < today and c.renew_months and c.renew_months > 0:
            c.renewal_date = _add_months(c.renewal_date, c.renew_months)
            n += 1
    if n:
        db.flush()
    return n


def contract_view(c: Contract, today: date) -> dict:
    deadline = c.renewal_date - timedelta(days=c.notice_days or 0)
    s: RecurringSeries | None = c.recurring
    amount = c.amount_cents if c.amount_cents is not None else (s.expected_amount_cents if s else None)
    days_to_deadline = (deadline - today).days
    if c.renewal_date < today:
        state = "termine"
    elif days_to_deadline < 0:
        state = "engage"  # trop tard pour résilier avant cette échéance
    elif days_to_deadline <= 30:
        state = "bientot"
    else:
        state = "ok"
    return {
        "id": c.id, "label": c.label, "recurring_id": c.recurring_id, "recurring_label": s.label if s else None,
        "frequency": s.frequency if s else None, "amount_cents": amount, "amount_from_recurring": c.amount_cents is None and s is not None,
        "renewal_date": c.renewal_date, "notice_days": c.notice_days, "renew_months": c.renew_months, "note": c.note,
        "deadline": deadline, "days_to_deadline": days_to_deadline, "state": state,
    }


def contracts_list(db: Session, today: date) -> list[dict]:
    roll_renewals(db, today)
    out = [contract_view(c, today) for c in db.scalars(select(Contract))]
    return sorted(out, key=lambda c: (c["state"] == "termine", c["deadline"]))


# --- Comparaison d'une année sur l'autre ---------------------------------------------------------------


def compare_periods(today: date, mode: str) -> tuple[tuple[date, date], tuple[date, date]]:
    """(période actuelle, même période un an plus tôt). ytd : du 1er janvier à aujourd'hui ; rolling : 12 derniers mois."""
    if mode == "rolling":
        cur_start = date(today.year, today.month, 1)
        cur = (_add_months(cur_start, -11), today)
    else:
        cur = (date(today.year, 1, 1), today)
    prev = (_add_months(cur[0], -12), _add_months(cur[1], -12))
    return cur, prev


def compare(db: Session, today: date, mode: str) -> dict:
    (a0, a1), (b0, b1) = compare_periods(today, mode)
    parents = dict(db.execute(select(Category.id, Category.parent_id)).all())
    rows = db.execute(
        select(Transaction.booked_at, Transaction.amount_cents, Transaction.category_id).where(
            Transaction.counted.is_(True), Transaction.is_transfer.is_(False), Transaction.booked_at >= b0, Transaction.booked_at <= a1
        )
    ).all()
    cats: dict[int | None, dict] = {}
    totals = {"cur": {"spent": 0, "income": 0}, "prev": {"spent": 0, "income": 0}}
    n_months = (a1.year - a0.year) * 12 + a1.month - a0.month + 1
    series = {"cur": [0] * n_months, "prev": [0] * n_months}
    for d, amount, cid in rows:
        side = "cur" if a0 <= d <= a1 else "prev" if b0 <= d <= b1 else None
        if side is None:
            continue
        start = a0 if side == "cur" else b0
        idx = (d.year - start.year) * 12 + d.month - start.month
        if amount > 0:
            totals[side]["income"] += amount
            continue
        totals[side]["spent"] -= amount
        if 0 <= idx < n_months:
            series[side][idx] -= amount
        top = (parents.get(cid) or cid) if cid is not None else None
        for key in {top, cid} if cid is not None and parents.get(cid) else {top}:
            e = cats.setdefault(key, {"category_id": key, "parent_id": parents.get(key) if key is not None else None, "cur_cents": 0, "prev_cents": 0})
            e[f"{side}_cents"] -= amount
    out = sorted(cats.values(), key=lambda e: -(e["cur_cents"] + e["prev_cents"]))
    for e in out:
        e["diff_cents"] = e["cur_cents"] - e["prev_cents"]
        e["diff_pct"] = round(e["diff_cents"] / e["prev_cents"], 3) if e["prev_cents"] else None
    labels = [_add_months(date(a0.year, a0.month, 1), i).strftime("%Y-%m") for i in range(n_months)]
    return {
        "mode": mode, "current": {"start": a0, "end": a1}, "previous": {"start": b0, "end": b1},
        "spent_cents": totals["cur"]["spent"], "prev_spent_cents": totals["prev"]["spent"],
        "income_cents": totals["cur"]["income"], "prev_income_cents": totals["prev"]["income"],
        "categories": out,
        "months": [{"month": m, "cur_cents": series["cur"][i], "prev_cents": series["prev"][i]} for i, m in enumerate(labels)],
    }
