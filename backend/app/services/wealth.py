"""Patrimoine : valorisation automatique des biens et crédits, vue d'ensemble (actifs, dettes, évolution)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, BalanceSnapshot, Transaction, utcnow
from app.services.balances import SPLIT_SOURCE, current_balance
from app.wealth import _add_months, computed_value, loan_schedule, monthly_payment, yearly_interest

PARAM_KEYS = {
    "bien": ("purchase_cents", "purchase_date", "depreciation_pct"),
    "credit": ("principal_cents", "rate_pct", "months", "first_payment", "insurance_cents"),
    "epargne": ("rate_pct", "ceiling_cents"),
}
HISTORY_MONTHS = 24


def refresh_valuations(db: Session, today: date) -> int:
    """Biens et crédits réglés : leur valeur du jour est enregistrée comme solde (patrimoine, accueil, widgets)."""
    changed = 0
    for acc in db.scalars(select(Account).where(Account.params.is_not(None), Account.type.in_(("bien", "credit")))):
        value = computed_value(acc.type, acc.params, today)
        if value is None:
            continue
        snap = db.scalar(select(BalanceSnapshot).where(BalanceSnapshot.account_id == acc.id, BalanceSnapshot.date == today))
        if snap is None:
            db.add(BalanceSnapshot(account_id=acc.id, date=today, balance_cents=value))
            changed += 1
        elif snap.balance_cents != value:
            snap.balance_cents, snap.recorded_at = value, utcnow()
            changed += 1
    if changed:
        db.flush()
    return changed


def clean_params(account_type: str, raw: dict) -> dict | None:
    keys = PARAM_KEYS.get(account_type, ())
    out = {k: raw[k] for k in keys if raw.get(k) not in (None, "")}
    for k in ("purchase_date", "first_payment"):
        if k in out:
            out[k] = str(out[k])[:10]
    return out or None


def _month_end(d: date) -> date:
    return date.fromordinal(_add_months(date(d.year, d.month, 1), 1).toordinal() - 1)


def _details(acc: Account, balance: int, today: date) -> dict:
    p = acc.params or {}
    if acc.type == "bien" and p.get("purchase_cents"):
        purchase = int(p["purchase_cents"])
        rate = float(p.get("depreciation_pct") or 0)
        return {"purchase_cents": purchase, "purchase_date": p.get("purchase_date"), "depreciation_pct": rate,
                "loss_cents": purchase - balance, "yearly_loss_cents": round(balance * rate / 100)}
    if acc.type == "credit" and p.get("principal_cents") and p.get("months") and p.get("first_payment"):
        principal, rate, months = int(p["principal_cents"]), float(p.get("rate_pct") or 0), int(p["months"])
        start = date.fromisoformat(str(p["first_payment"]))
        sched = loan_schedule(principal, rate, months, start)
        future = [i for i in sched if i.date > today]
        return {
            "principal_cents": principal, "rate_pct": rate, "months": months, "first_payment": str(start),
            "insurance_cents": int(p.get("insurance_cents") or 0),
            "monthly_payment_cents": monthly_payment(principal, rate, months), "end_date": str(sched[-1].date) if sched else None,
            "remaining_cents": -balance, "paid_pct": round(1 - (-balance) / principal, 3) if principal else 1.0,
            "interest_left_cents": sum(i.interest_cents for i in future), "payments_left": len(future),
            "schedule": [{"n": i.n, "date": str(i.date), "payment_cents": i.payment_cents, "interest_cents": i.interest_cents,
                          "principal_cents": i.principal_cents, "remaining_cents": i.remaining_cents} for i in sched],
        }
    if acc.type == "epargne" and p.get("rate_pct") is not None:
        rate = float(p.get("rate_pct") or 0)
        ceiling = int(p["ceiling_cents"]) if p.get("ceiling_cents") else None
        return {"rate_pct": rate, "ceiling_cents": ceiling, "yearly_interest_cents": yearly_interest(balance, rate, ceiling),
                "room_cents": (ceiling - balance) if ceiling else None, "at_ceiling": bool(ceiling and balance >= ceiling)}
    return {}


def overview(db: Session, today: date) -> dict:
    refresh_valuations(db, today)
    accounts = list(db.scalars(select(Account).where(Account.is_archived.is_(False)).order_by(Account.type, Account.name)))
    rows, assets, debts = [], 0, 0
    for acc in accounts:
        bal = current_balance(db, acc.id)[0] or 0
        counted = acc.include_in_net_worth
        if counted:
            if bal >= 0:
                assets += bal
            else:
                debts += -bal
        rows.append({"id": acc.id, "name": acc.name, "type": acc.type, "balance_cents": bal, "in_net_worth": counted,
                     "params": acc.params or {}, "details": _details(acc, bal, today)})

    # Évolution sur 24 mois (fin de chaque mois) : biens et crédits réglés d'après leur calcul ; les autres comptes
    # d'après leur solde actuel moins les opérations postérieures.
    first = _add_months(date(today.year, today.month, 1), -(HISTORY_MONTHS - 1))
    months = [_add_months(first, i) for i in range(HISTORY_MONTHS)]
    ends = [min(_month_end(m), today) for m in months]
    in_nw = [a for a in accounts if a.include_in_net_worth]
    plain = [a for a in in_nw if computed_value(a.type, a.params, today) is None]
    per_month: dict[tuple[int, int], int] = defaultdict(int)
    if plain:
        for booked, amount in db.execute(
            select(Transaction.booked_at, Transaction.amount_cents).where(
                Transaction.account_id.in_([a.id for a in plain]), Transaction.booked_at >= first, Transaction.booked_at <= today,
                Transaction.source != SPLIT_SOURCE,
            )
        ):
            per_month[(booked.year, booked.month)] += amount
    plain_now = sum(r["balance_cents"] for r in rows if r["id"] in {a.id for a in plain})
    history = []
    later = 0
    worth: dict[date, int] = {}
    for m in reversed(months):
        worth[m] = plain_now - later
        later += per_month.get((m.year, m.month), 0)
    for m, end in zip(months, ends):
        computed = sum(v for a in in_nw if a not in plain and (v := computed_value(a.type, a.params, end)) is not None)
        history.append({"month": m.strftime("%Y-%m"), "net_worth_cents": worth[m] + computed})

    interest = sum(r["details"].get("yearly_interest_cents", 0) for r in rows if r["type"] == "epargne")
    return {
        "today": today,
        "assets_cents": assets,
        "debts_cents": debts,
        "net_worth_cents": assets - debts,
        "yearly_interest_cents": interest,
        "accounts": rows,
        "history": history,
    }
