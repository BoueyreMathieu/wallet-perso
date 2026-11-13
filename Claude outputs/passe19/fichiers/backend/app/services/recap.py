"""Bilan d'un mois : revenus, dépenses par couche et par catégorie (comparées au mois d'avant et à l'habitude),
plus grosses dépenses, nouveaux vendeurs, épargne, jours sans dépense et quelques phrases-clés."""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.dashboard import savings_flows
from app.models import Category, RecurringSeries, Transaction
from app.services.planning import category_natures, layer_of


def _bounds(m: date) -> tuple[date, date]:
    return m, m.replace(day=calendar.monthrange(m.year, m.month)[1])


def _shift(m: date, n: int) -> date:
    idx = m.year * 12 + m.month - 1 + n
    return date(idx // 12, idx % 12 + 1, 1)


def _rows(db: Session, lo: date, hi: date) -> list[Transaction]:
    return db.scalars(
        select(Transaction).options(selectinload(Transaction.merchant)).where(
            Transaction.booked_at >= lo, Transaction.booked_at <= hi, Transaction.counted.is_(True), Transaction.is_transfer.is_(False),
        )
    ).all()


def recap(db: Session, month: date, today: date) -> dict:
    lo, hi = _bounds(month)
    end = min(hi, today)
    parents = dict(db.execute(select(Category.id, Category.parent_id)).all())
    names = dict(db.execute(select(Category.id, Category.name)).all())
    natures = category_natures(db)
    top = lambda cid: (parents.get(cid) or cid) if cid is not None else None  # noqa: E731

    rows = _rows(db, lo, hi)
    income = sum(t.amount_cents for t in rows if t.amount_cents > 0)
    out_rows = [t for t in rows if t.amount_cents < 0]
    spending = -sum(t.amount_cents for t in out_rows)
    layers = {"fixe": 0, "essentiel": 0, "plaisir": 0}
    by_cat: dict[int | None, int] = defaultdict(int)
    for t in out_rows:
        layers[layer_of(t.category_id, t.recurring_id, natures)] -= t.amount_cents
        by_cat[top(t.category_id)] -= t.amount_cents

    # Comparaisons : mois précédent et habitude (moyenne des 3 mois d'avant).
    prev_by_cat: dict[int | None, int] = defaultdict(int)
    usual_by_cat: dict[int | None, float] = defaultdict(float)
    prev_income = prev_spending = 0
    for k in (1, 2, 3):
        plo, phi = _bounds(_shift(month, -k))
        for t in _rows(db, plo, phi):
            if t.amount_cents < 0:
                usual_by_cat[top(t.category_id)] -= t.amount_cents / 3
                if k == 1:
                    prev_by_cat[top(t.category_id)] -= t.amount_cents
                    prev_spending -= t.amount_cents
            elif k == 1:
                prev_income += t.amount_cents
    categories = sorted(
        ({"category_id": cid, "name": names.get(cid, "À catégoriser") if cid else "À catégoriser", "amount_cents": v,
          "previous_cents": prev_by_cat.get(cid, 0), "usual_cents": round(usual_by_cat.get(cid, 0))}
         for cid, v in by_cat.items()),
        key=lambda c: -c["amount_cents"],
    )

    biggest = sorted(out_rows, key=lambda t: t.amount_cents)[:5]
    first_seen = dict(db.execute(
        select(Transaction.merchant_id, func.min(Transaction.booked_at)).where(Transaction.merchant_id.is_not(None)).group_by(Transaction.merchant_id)
    ).all())
    new_merchants: dict[str, int] = defaultdict(int)
    for t in out_rows:
        if t.merchant_id is not None and lo <= first_seen.get(t.merchant_id, lo - timedelta(days=1)) <= hi:
            new_merchants[t.merchant.name] -= t.amount_cents
    spend_days = {t.booked_at for t in out_rows if t.recurring_id is None}
    days = (end - lo).days + 1
    saved = sum(v for _, v in savings_flows(db, lo, hi, []))
    increases = db.scalars(select(RecurringSeries).where(
        RecurringSeries.price_changed_on >= lo, RecurringSeries.price_changed_on <= hi, RecurringSeries.previous_amount_cents.is_not(None),
    )).all()

    highlights: list[str] = []
    for c in categories:
        if c["usual_cents"] >= 3000 and c["category_id"] is not None and hi <= today:
            d = c["amount_cents"] - c["usual_cents"]
            if abs(d) >= max(2000, 0.25 * c["usual_cents"]):
                highlights.append(f"{c['name']} : {'+' if d > 0 else '−'}{abs(d) // 100} € par rapport à d'habitude")
    highlights = highlights[:4]

    return {
        "month": month.strftime("%Y-%m"),
        "complete": hi < today,
        "income_cents": income,
        "spending_cents": spending,
        "net_cents": income - spending,
        "saved_cents": saved,
        "savings_rate": round((income - spending) / income, 3) if income > 0 else None,
        "previous": {"income_cents": prev_income, "spending_cents": prev_spending},
        "layers": layers,
        "categories": categories,
        "biggest": [{"id": t.id, "date": t.booked_at, "label": t.merchant.name if t.merchant else t.raw_label.split(" | ")[0][:80],
                     "amount_cents": t.amount_cents, "category_id": t.category_id} for t in biggest],
        "new_merchants": [{"name": n, "amount_cents": v} for n, v in sorted(new_merchants.items(), key=lambda kv: -kv[1])[:6]],
        "no_spend_days": max(days - len(spend_days), 0),
        "days": days,
        "price_increases": [{"label": s.label, "from_cents": s.previous_amount_cents, "to_cents": s.expected_amount_cents} for s in increases],
        "highlights": highlights,
    }
