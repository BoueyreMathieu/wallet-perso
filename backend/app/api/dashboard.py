"""Tableau de bord : un condensé du mois et des 12 derniers mois, calculé à la volée.

Statistiques = opérations comptées (counted) et hors transferts (is_transfer = False), comme partout.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.services.backup_status import backup_status
from app.models import Account, Category, Connection, PendingTransaction, Transaction
from app.security import require_auth
from app.seed import resolve_paths
from app.services.balances import current_balance, SPLIT_SOURCE

router = APIRouter(prefix="/api/dashboard", tags=["tableau de bord"], dependencies=[Depends(require_auth)])


class CategorySpend(BaseModel):
    category_id: int | None  # catégorie principale (None = à catégoriser)
    spent_cents: int
    prev_spent_cents: int
    count: int


class MonthPoint(BaseModel):
    month: str  # AAAA-MM
    income_cents: int
    spent_cents: int
    saved_cents: int = 0  # versé net vers les comptes d'épargne / investissement
    net_worth_cents: int | None = None


class TopExpense(BaseModel):
    id: int
    booked_at: date
    label: str
    amount_cents: int
    category_id: int | None
    account_name: str


class TopMerchant(BaseModel):
    merchant_id: int | None
    name: str
    spent_cents: int
    count: int


class BudgetAlert(BaseModel):
    category_id: int
    level: str  # alerte | depasse


class Todo(BaseModel):
    to_categorize_ops: int
    to_categorize_merchants: int
    connections_to_renew: list[str]
    connections_in_error: list[str]
    last_sync_at: datetime | None
    backup_warning: str | None = None
    recurring_to_confirm: int = 0  # abonnements / récurrents détectés, à confirmer
    price_increases: list[str] = []  # hausses de prix récentes d'abonnements
    budget_alerts: list[BudgetAlert] = []  # budgets du mois dépassés ou en passe de l'être


class FocusTransaction(BaseModel):
    id: int
    booked_at: date
    label: str
    amount_cents: int
    category_id: int | None
    account_name: str


class Dashboard(BaseModel):
    month: str
    focus_category_id: int | None = None  # vue « une seule catégorie » (sous-catégories en détail)
    transactions: list[FocusTransaction] = []  # opérations du mois (comptées, hors virements)
    start: date
    end: date
    is_current: bool
    spent_cents: int
    income_cents: int
    prev_spent_same_day_cents: int  # mois précédent, à la même date
    prev_spent_cents: int  # mois précédent complet
    prev_income_cents: int
    prev_income_same_day_cents: int = 0  # revenus de la période précédente, à la même date
    daily_cumulative: list[int]  # dépenses cumulées jour par jour (mois choisi)
    prev_daily_cumulative: list[int]
    by_category: list[CategorySpend]
    top_expenses: list[TopExpense]
    top_merchants: list[TopMerchant]
    months: list[MonthPoint]
    period: str = "month"  # « month » (un mois calendaire) ou « period » (dates choisies)
    pending_spent_cents: int = 0  # dépenses « à venir » (pas encore comptabilisées) des comptes choisis
    saved_cents: int = 0  # épargne de la période : versé net vers l'épargne (livrets, investissements…)
    prev_saved_cents: int = 0
    savings_rate: float | None  # épargne versée / revenus, sur la période
    savings_rate_3m: float | None = None  # idem, sur les 3 derniers mois complets
    todo: Todo


def _month_bounds(y: int, m: int) -> tuple[date, date]:
    start = date(y, m, 1)
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return start, nxt - timedelta(days=1)


def _shift(y: int, m: int, delta: int) -> tuple[int, int]:
    idx = y * 12 + (m - 1) + delta
    return idx // 12, idx % 12 + 1


def _label(t: Transaction) -> str:
    if t.merchant:
        return t.merchant.name
    parts = t.raw_label.split(" | ")
    return parts[1] if len(parts) > 1 else parts[0]


SAVINGS_TYPES = {"epargne", "investissement"}
SAVINGS_CATEGORY = "Transferts/Épargne / investissement"


def savings_flows(db: Session, lo: date, hi: date, account_ids: list[int]) -> list[tuple[date, int]]:
    """Argent versé vers l'épargne (+) ou retiré de l'épargne (−), jour par jour.

    - côté compte courant (ou autre compte non-épargne) : virement apparié vers un compte d'épargne /
      d'investissement, ou virement rangé dans « Transferts › Épargne / investissement » (livret pas dans l'appli) ;
    - côté compte d'épargne : seulement si l'autre côté n'est pas déjà compté (hors appli ou non sélectionné).
    Les mouvements entre deux comptes d'épargne ne comptent pas.
    """
    types = dict(db.execute(select(Account.id, Account.type)).all())
    selected = set(account_ids) or set(types)
    sav_cats = {cid for path, cid in resolve_paths(db).items() if path == SAVINGS_CATEGORY}
    rows = db.scalars(
        select(Transaction).where(
            Transaction.booked_at >= lo,
            Transaction.booked_at <= hi,
            Transaction.is_transfer.is_(True),
            Transaction.counted.is_(True),
            Transaction.account_id.in_(selected),
        )
    ).all()
    pair_ids = [t.transfer_pair_id for t in rows if t.transfer_pair_id and (t.details or {}).get("virement_interne")]
    pair_account = dict(db.execute(select(Transaction.id, Transaction.account_id).where(Transaction.id.in_(pair_ids))).all()) if pair_ids else {}
    out: list[tuple[date, int]] = []
    for t in rows:
        other = pair_account.get(t.transfer_pair_id) if (t.details or {}).get("virement_interne") else None
        other_is_sav = other is not None and types.get(other) in SAVINGS_TYPES
        if types.get(t.account_id) not in SAVINGS_TYPES:
            if other_is_sav or (other is None and t.category_id in sav_cats):
                out.append((t.booked_at, -t.amount_cents))
        elif not other_is_sav and (other is None or other not in selected):
            out.append((t.booked_at, t.amount_cents))
    return out


@router.get("", response_model=Dashboard)
def dashboard(
    month: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    accounts: str | None = Query(default=None, description="ids de comptes séparés par des virgules (vide = tous)"),
    category_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Un mois (month=AAAA-MM, par défaut le mois en cours) ou une période (date_from / date_to).
    La période de comparaison est le mois précédent, ou la période de même durée juste avant."""
    today = date.today()
    try:
        account_ids = [int(x) for x in accounts.split(",") if x.strip()] if accounts else []
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "accounts : liste d'identifiants attendue") from e

    if date_from or date_to:
        mode = "period"
        end = date_to or today
        if date_from is None:
            q0 = select(func.min(Transaction.booked_at))
            if account_ids:
                q0 = q0.where(Transaction.account_id.in_(account_ids))
            start = db.scalar(q0) or end
        else:
            start = date_from
        if start > end:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La date de début doit précéder la date de fin")
        length = (end - start).days + 1
        pend = start - timedelta(days=1)
        pstart = pend - timedelta(days=length - 1)
        y, m = end.year, end.month
    else:
        mode = "month"
        if month:
            try:
                y, m = (int(x) for x in month.split("-"))
                date(y, m, 1)
            except ValueError as e:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Mois attendu au format AAAA-MM") from e
        else:
            y, m = today.year, today.month
        start, end = _month_bounds(y, m)
        py, pm = _shift(y, m, -1)
        pstart, pend = _month_bounds(py, pm)
    is_current = start <= today <= end
    elapsed = (min(today, end) - start).days  # jours écoulés dans la période (comparaison « à la même date »)

    # Graphique mensuel : au moins 12 mois, jusqu'au mois de fin (36 au plus).
    n_months = min(max(12, (end.year - start.year) * 12 + end.month - start.month + 1), 36)
    oy, om = _shift(end.year, end.month, -(n_months - 1))
    first = date(oy, om, 1)

    parents = dict(db.execute(select(Category.id, Category.parent_id)).all())
    if category_id is not None and category_id not in parents:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Catégorie introuvable")
    focus_ids = None
    if category_id is not None:
        focus_ids = {category_id} | {cid for cid, pid in parents.items() if pid == category_id}

    lo = min(first, pstart)
    q = (
        select(Transaction)
        .options(selectinload(Transaction.merchant), selectinload(Transaction.account))
        .where(
            Transaction.booked_at >= lo,
            Transaction.booked_at <= end,
            Transaction.counted.is_(True),
            Transaction.is_transfer.is_(False),
        )
    )
    if account_ids:
        q = q.where(Transaction.account_id.in_(account_ids))
    if focus_ids is not None:
        q = q.where(Transaction.category_id.in_(focus_ids))
    txs = db.scalars(q).all()

    def top(cid: int | None) -> int | None:
        if cid is None:
            return None
        if focus_ids is not None:
            return cid  # vue catégorie : détail par sous-catégorie
        return parents.get(cid) or cid

    cur = [t for t in txs if start <= t.booked_at <= end]
    prev = [t for t in txs if pstart <= t.booked_at <= pend]
    spent = lambda rows: -sum(t.amount_cents for t in rows if t.amount_cents < 0)  # noqa: E731
    income = lambda rows: sum(t.amount_cents for t in rows if t.amount_cents > 0)  # noqa: E731
    prev_same_day = [t for t in prev if (t.booked_at - pstart).days <= elapsed]

    def cumulative(rows: list[Transaction], origin: date, days: int) -> list[int]:
        per_day: dict[int, int] = defaultdict(int)
        for t in rows:
            if t.amount_cents < 0:
                per_day[(t.booked_at - origin).days] -= t.amount_cents
        out, total = [], 0
        for d in range(days):
            total += per_day[d]
            out.append(total)
        return out

    cats: dict[int | None, dict[str, int]] = defaultdict(lambda: {"spent": 0, "prev": 0, "count": 0})
    for t in cur:
        if t.amount_cents < 0:
            c = cats[top(t.category_id)]
            c["spent"] -= t.amount_cents
            c["count"] += 1
    for t in prev:
        if t.amount_cents < 0:
            cats[top(t.category_id)]["prev"] -= t.amount_cents
    by_category = sorted(
        (CategorySpend(category_id=k, spent_cents=v["spent"], prev_spent_cents=v["prev"], count=v["count"]) for k, v in cats.items()),
        key=lambda c: (-c.spent_cents, -c.prev_spent_cents),
    )

    expenses = sorted((t for t in cur if t.amount_cents < 0), key=lambda t: t.amount_cents)[:5]
    merchants: dict[int | None, dict] = {}
    for t in cur:
        if t.amount_cents < 0 and t.merchant_id is not None:
            e = merchants.setdefault(t.merchant_id, {"name": t.merchant.name if t.merchant else "?", "spent": 0, "count": 0})
            e["spent"] -= t.amount_cents
            e["count"] += 1
    top_merchants = sorted(merchants.items(), key=lambda kv: -kv[1]["spent"])[:5]

    # Épargne versée (hors vue catégorie : elle ne concerne pas une catégorie de dépense).
    flows = savings_flows(db, lo, end, account_ids) if focus_ids is None else []
    saved = lambda a, b: sum(v for d, v in flows if a <= d <= b)  # noqa: E731

    # Mois : revenus / dépenses / épargne + patrimoine estimé en fin de mois.
    acc_q = select(Account).where(Account.is_archived.is_(False), Account.include_in_net_worth.is_(True))
    if account_ids:
        acc_q = acc_q.where(Account.id.in_(account_ids))
    nw_accounts = db.scalars(acc_q).all()
    net_now = 0
    for acc in nw_accounts:
        bal, _ = current_balance(db, acc.id)
        net_now += bal or 0
    acc_ids = [a.id for a in nw_accounts]
    all_after = defaultdict(int)  # somme des opérations (toutes) par mois, pour remonter le patrimoine
    if acc_ids:
        for booked, amount in db.execute(
            select(Transaction.booked_at, Transaction.amount_cents).where(
                Transaction.account_id.in_(acc_ids), Transaction.booked_at >= first, Transaction.booked_at <= today,
                Transaction.source != SPLIT_SOURCE,
            )
        ).all():
            all_after[(booked.year, booked.month)] += amount

    months: list[MonthPoint] = []
    for i in range(n_months):
        yy, mm = _shift(oy, om, i)
        ms, me = _month_bounds(yy, mm)
        rows = [t for t in txs if ms <= t.booked_at <= me]
        nw = None
        if me <= today or (ms <= today <= me):
            later = sum(v for (ay, am), v in all_after.items() if (ay, am) > (yy, mm))
            nw = net_now - later
        months.append(
            MonthPoint(month=f"{yy:04d}-{mm:02d}", income_cents=income(rows), spent_cents=spent(rows), saved_cents=saved(ms, me), net_worth_cents=nw)
        )

    def rate(sv: int, inc: int) -> float | None:
        return round(sv / inc, 3) if inc > 0 else None

    # Les 3 derniers mois complets (calculés à part : ils peuvent sortir de la fenêtre affichée).
    ty, tm = today.year, today.month
    l3_start, l3_end = date(*_shift(ty, tm, -3), 1), date(ty, tm, 1) - timedelta(days=1)
    if focus_ids is None:
        q3 = select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.booked_at >= l3_start, Transaction.booked_at <= l3_end, Transaction.amount_cents > 0,
            Transaction.counted.is_(True), Transaction.is_transfer.is_(False),
        )
        if account_ids:
            q3 = q3.where(Transaction.account_id.in_(account_ids))
        savings_rate_3m = rate(sum(v for _, v in savings_flows(db, l3_start, l3_end, account_ids)), int(db.scalar(q3) or 0))
    else:
        savings_rate_3m = None

    # À traiter.
    n_ops, n_merch = db.execute(
        select(func.count(Transaction.id), func.count(func.distinct(Transaction.merchant_id))).where(Transaction.category_id.is_(None))
    ).one()
    soon = datetime.now(timezone.utc) + timedelta(days=14)
    renew, errors, last_sync = [], [], None
    for c in db.scalars(select(Connection)):
        exp = c.consent_expires_at.replace(tzinfo=c.consent_expires_at.tzinfo or timezone.utc) if c.consent_expires_at else None
        if c.status == "expire" or (exp and exp < soon):
            renew.append(c.label)
        elif c.status in ("erreur", "en_attente"):
            errors.append(c.label)
        if c.last_sync_at and (last_sync is None or c.last_sync_at > last_sync):
            last_sync = c.last_sync_at

    # Opérations de la période (détail des cartes du haut, et paiements de la vue catégorie).
    focus_txs = [
        FocusTransaction(id=t.id, booked_at=t.booked_at, label=_label(t), amount_cents=t.amount_cents, category_id=t.category_id, account_name=t.account.name)
        for t in sorted(cur, key=lambda t: (t.booked_at, t.id), reverse=True)
    ][:2000]

    period_saved = saved(start, end)
    pq = select(func.coalesce(func.sum(PendingTransaction.amount_cents), 0)).where(PendingTransaction.amount_cents < 0)
    if account_ids:
        pq = pq.where(PendingTransaction.account_id.in_(account_ids))
    if focus_ids is not None:
        pq = pq.where(PendingTransaction.category_id.in_(focus_ids))
    pending_spent = -int(db.scalar(pq) or 0)
    return Dashboard(
        month=f"{y:04d}-{m:02d}",
        period=mode,
        pending_spent_cents=pending_spent if is_current else 0,
        focus_category_id=category_id,
        transactions=focus_txs,
        start=start,
        end=end,
        is_current=is_current,
        spent_cents=spent(cur),
        income_cents=income(cur),
        prev_spent_same_day_cents=spent(prev_same_day),
        prev_spent_cents=spent(prev),
        prev_income_cents=income(prev),
        prev_income_same_day_cents=income(prev_same_day),
        daily_cumulative=cumulative(cur, start, elapsed + 1 if is_current else (end - start).days + 1),
        prev_daily_cumulative=cumulative(prev, pstart, (pend - pstart).days + 1),
        by_category=by_category,
        top_expenses=[
            TopExpense(id=t.id, booked_at=t.booked_at, label=_label(t), amount_cents=t.amount_cents, category_id=t.category_id, account_name=t.account.name)
            for t in expenses
        ],
        top_merchants=[TopMerchant(merchant_id=k, name=v["name"], spent_cents=v["spent"], count=v["count"]) for k, v in top_merchants],
        months=months,
        saved_cents=period_saved,
        prev_saved_cents=saved(pstart, pend),
        savings_rate=rate(period_saved, income(cur)) if focus_ids is None else None,
        savings_rate_3m=savings_rate_3m,
        todo=Todo(
            to_categorize_ops=int(n_ops or 0),
            to_categorize_merchants=int(n_merch or 0),
            connections_to_renew=renew,
            connections_in_error=errors,
            last_sync_at=last_sync,
            backup_warning=backup_status(db)["warning"],
            **_planning_todo(db, today),
        ),
    )


def _planning_todo(db: Session, today: date) -> dict:
    """Récurrents à confirmer, hausses de prix, budgets en alerte (jamais bloquant pour l'accueil)."""
    from app.api.planning import recurring_alerts
    from app.services.planning import budgets_overview

    try:
        rec = recurring_alerts(db, today)
        budgets = budgets_overview(db, today, today)["items"]
    except Exception:  # noqa: BLE001
        return {}
    return {
        "recurring_to_confirm": rec["to_confirm"],
        "price_increases": rec["price_increases"],
        "budget_alerts": [BudgetAlert(category_id=b["category_id"], level=b["level"]) for b in budgets if b["level"] != "ok"],
    }


@router.get("/months", response_model=list[MonthPoint])
def months_history(
    accounts: str | None = Query(default=None, description="ids de comptes séparés par des virgules (vide = tous)"),
    category_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Tout l'historique mois par mois (10 ans au plus), pour le graphique qu'on fait défiler."""
    today = date.today()
    try:
        account_ids = [int(x) for x in accounts.split(",") if x.strip()] if accounts else []
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "accounts : liste d'identifiants attendue") from e
    parents = dict(db.execute(select(Category.id, Category.parent_id)).all())
    if category_id is not None and category_id not in parents:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Catégorie introuvable")
    focus_ids = {category_id} | {cid for cid, pid in parents.items() if pid == category_id} if category_id is not None else None

    q0 = select(func.min(Transaction.booked_at))
    if account_ids:
        q0 = q0.where(Transaction.account_id.in_(account_ids))
    earliest = db.scalar(q0) or today
    n_months = min(max(12, (today.year - earliest.year) * 12 + today.month - earliest.month + 1), 120)
    oy, om = _shift(today.year, today.month, -(n_months - 1))
    first = date(oy, om, 1)

    q = select(Transaction.booked_at, Transaction.amount_cents).where(
        Transaction.booked_at >= first, Transaction.booked_at <= today,
        Transaction.counted.is_(True), Transaction.is_transfer.is_(False),
    )
    if account_ids:
        q = q.where(Transaction.account_id.in_(account_ids))
    if focus_ids is not None:
        q = q.where(Transaction.category_id.in_(focus_ids))
    inc: dict[tuple[int, int], int] = defaultdict(int)
    out: dict[tuple[int, int], int] = defaultdict(int)
    for booked, amount in db.execute(q).all():
        key = (booked.year, booked.month)
        if amount > 0:
            inc[key] += amount
        else:
            out[key] -= amount
    saved: dict[tuple[int, int], int] = defaultdict(int)
    if focus_ids is None:
        for d, v in savings_flows(db, first, today, account_ids):
            saved[(d.year, d.month)] += v

    # Patrimoine en fin de mois : solde actuel moins les opérations postérieures.
    acc_q = select(Account).where(Account.is_archived.is_(False), Account.include_in_net_worth.is_(True))
    if account_ids:
        acc_q = acc_q.where(Account.id.in_(account_ids))
    nw_accounts = db.scalars(acc_q).all()
    net_now = sum((current_balance(db, a.id)[0] or 0) for a in nw_accounts)
    per_month: dict[tuple[int, int], int] = defaultdict(int)
    if nw_accounts:
        for booked, amount in db.execute(
            select(Transaction.booked_at, Transaction.amount_cents).where(
                Transaction.account_id.in_([a.id for a in nw_accounts]), Transaction.booked_at >= first, Transaction.booked_at <= today,
                Transaction.source != SPLIT_SOURCE,
            )
        ).all():
            per_month[(booked.year, booked.month)] += amount

    points: list[MonthPoint] = []
    later = 0  # opérations des mois après celui qu'on calcule
    keys = [_shift(oy, om, i) for i in range(n_months)]
    worth: dict[tuple[int, int], int] = {}
    for key in reversed(keys):
        worth[key] = net_now - later
        later += per_month.get(key, 0)
    for yy, mm in keys:
        points.append(
            MonthPoint(
                month=f"{yy:04d}-{mm:02d}",
                income_cents=inc.get((yy, mm), 0),
                spent_cents=out.get((yy, mm), 0),
                saved_cents=saved.get((yy, mm), 0),
                net_worth_cents=worth[(yy, mm)],
            )
        )
    return points
