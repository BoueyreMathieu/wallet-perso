"""Budgets mensuels, prévision de trésorerie et projection.

Le solde prévu se construit en couches :
- **socle** : solde actuel + revenus (récurrents à leur date + revenus habituels) − charges fixes (récurrents à leur
  date + factures irrégulières) ± virements programmés ;
- **essentiels** puis **plaisirs** : la tendance de chaque catégorie (moyenne pondérée de tout l'historique, voir
  app/trends.py), répartie jour par jour selon tes habitudes (jours de la semaine, période du mois).

Scénario (« et si… ») : plaisirs à X %, budgets appliqués comme plafonds, objectifs par catégorie, épargne en plus.
Dépenses = opérations comptées, hors virements entre comptes, montants négatifs (comme le tableau de bord).
"""

from __future__ import annotations

import calendar
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.layers import NATURES, effective_natures
from app.models import Account, Budget, Category, Merchant, PendingTransaction, RecurringSeries, Transaction
from app.recurrence import FREQUENCIES, monthly_cost, occurrences
from app.seed import get_meta, resolve_paths
from app.services.balances import current_balance
from app.services.recurring import ACTIVE_STATUSES
from app.trends import (
    HABIT_WINDOW_DAYS, MAX_MONTHS, Habit, Occasional, Profile, apply_caps, band, classify, direction, learn_habit, learn_profile,
    rest_of_month, trend_level, unit_expected, weighted_level,
)

# Comptes pris par défaut pour la trésorerie : l'argent disponible au quotidien.
LIQUID_TYPES = ("courant", "paypal")


def month_bounds(d: date) -> tuple[date, date]:
    return d.replace(day=1), d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _shift_month(d: date, n: int) -> date:
    idx = d.year * 12 + d.month - 1 + n
    return date(idx // 12, idx % 12 + 1, 1)


def _family(parents: dict[int, int | None], cid: int) -> set[int]:
    """La catégorie et ses sous-catégories."""
    return {cid} | {c for c, p in parents.items() if p == cid}


def _expenses(db: Session, lo: date, hi: date, account_ids: list[int] | None = None):
    q = select(Transaction.id, Transaction.booked_at, Transaction.amount_cents, Transaction.category_id, Transaction.recurring_id).where(
        Transaction.booked_at >= lo,
        Transaction.booked_at <= hi,
        Transaction.counted.is_(True),
        Transaction.is_transfer.is_(False),
        Transaction.amount_cents < 0,
    )
    if account_ids:
        q = q.where(Transaction.account_id.in_(account_ids))
    return db.execute(q).all()


def _active_series(db: Session) -> list[RecurringSeries]:
    return db.scalars(select(RecurringSeries).where(RecurringSeries.status.in_(ACTIVE_STATUSES))).all()


def category_natures(db: Session) -> dict[int, str]:
    rows = db.execute(select(Category.id, Category.parent_id, Category.nature)).all()
    return effective_natures({r.id: r.nature for r in rows}, {r.id: r.parent_id for r in rows}, resolve_paths(db))


def layer_of(category_id: int | None, recurring_id: int | None, natures: dict[int, str]) -> str:
    if recurring_id is not None:
        return "fixe"
    return natures.get(category_id, "essentiel") if category_id is not None else "essentiel"


def default_accounts(db: Session) -> list[int]:
    return list(
        db.scalars(select(Account.id).where(Account.is_archived.is_(False), Account.type.in_(LIQUID_TYPES)).order_by(Account.id))
    )


# --- Modèle de tendances ------------------------------------------------------------------------


@dataclass
class Unit:
    """Une catégorie de dépenses sans date fixe : sa tendance mensuelle."""

    category_id: int | None
    layer: str
    monthly: int
    direction: str
    history: list[int]
    lo: float = 0.85  # mois « bon » / niveau (prévision optimiste)
    hi: float = 1.15  # mois « mauvais » / niveau (prévision prudente)
    occasional: Occasional | None = None  # de temps en temps : un montant d'un coup à la prochaine date attendue


@dataclass
class Model:
    units: dict[int | None, Unit] = field(default_factory=dict)
    profiles: dict[str, Profile] = field(default_factory=dict)
    other_income: int = 0
    other_income_direction: str = "stable"
    other_income_day: int = 28  # jour du mois où ils sont arrivés pour 80 % (au plus tard)
    months_used: int = 0
    habits: dict[int | None, list[Habit]] = field(default_factory=dict)  # vendeurs habituels, par catégorie
    spent_month: dict[int | None, int] = field(default_factory=dict)  # déjà dépensé ce mois-ci (hors récurrents), par catégorie


def build_model(db: Session, today: date, account_ids: list[int] | None) -> Model:
    """Tendances des dépenses sans date fixe (hors récurrents) et des revenus non récurrents, sur les 12 derniers
    mois complets (à partir du premier mois où il y a des opérations)."""
    natures = category_natures(db)
    last = today.replace(day=1) - timedelta(days=1)
    first = _shift_month(today, -MAX_MONTHS)
    q = select(Transaction.booked_at).where(Transaction.counted.is_(True))
    if account_ids:
        q = q.where(Transaction.account_id.in_(account_ids))
    oldest = db.scalar(q.order_by(Transaction.booked_at).limit(1))
    months = [_shift_month(first, i) for i in range(MAX_MONTHS)]
    if oldest is not None:
        months = [m for m in months if month_bounds(m)[1] >= oldest]
    else:
        months = []
    keys = [m.strftime("%Y-%m") for m in months]
    model = Model(months_used=len(keys))
    if not keys:
        model.profiles = {n: Profile() for n in (*NATURES, "revenu")}
        return model

    per_unit: dict[int | None, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    income: dict[str, int] = defaultdict(int)
    daily: dict[str, list[tuple[date, int]]] = defaultdict(list)
    visits: dict[int | None, list[tuple[date, int]]] = defaultdict(list)  # achats datés (mois en cours compris)
    q = select(Transaction.booked_at, Transaction.amount_cents, Transaction.category_id).where(
        Transaction.booked_at >= months[0], Transaction.booked_at <= today,
        Transaction.counted.is_(True), Transaction.is_transfer.is_(False), Transaction.recurring_id.is_(None),
    )
    if account_ids:
        q = q.where(Transaction.account_id.in_(account_ids))
    for r in db.execute(q).all():
        if r.amount_cents < 0:
            visits[r.category_id].append((r.booked_at, -r.amount_cents))
        if r.booked_at > last:
            continue  # mois en cours : seulement pour les dates d'achat (les tendances portent sur des mois complets)
        k = r.booked_at.strftime("%Y-%m")
        if r.amount_cents > 0:
            income[k] += r.amount_cents
            daily["revenu"].append((r.booked_at, r.amount_cents))
        else:
            per_unit[r.category_id][k] -= r.amount_cents
            daily[layer_of(r.category_id, None, natures)].append((r.booked_at, -r.amount_cents))

    # Catégories « fixes » déjà couvertes par un récurrent (loyer, énergie…) : leur reste n'est pas une charge de plus
    # (sinon doublon : l'échéance du récurrent + la tendance de la catégorie).
    q = select(Transaction.category_id).where(
        Transaction.recurring_id.is_not(None), Transaction.booked_at >= _shift_month(today, -4), Transaction.category_id.is_not(None),
    ).distinct()
    if account_ids:
        q = q.where(Transaction.account_id.in_(account_ids))
    covered = set(db.scalars(q))

    for cid, by_month in per_unit.items():
        if cid in covered and layer_of(cid, None, natures) == "fixe":
            continue
        hist = [by_month[k] for k in keys]
        while hist and hist[0] == 0:  # mois avant la première dépense de la catégorie : pas des mois « à 0 € »
            hist.pop(0)
        kind = classify(hist, visits.get(cid, []), today)
        if kind is None:
            continue  # une seule fois (formation, gros achat…) ou arrêté depuis longtemps : pas prévu
        if isinstance(kind, Occasional):
            model.units[cid] = Unit(cid, layer_of(cid, None, natures), round(kind.monthly), direction(hist), hist, 0.8, 1.2, kind)
            continue
        level = trend_level(hist)
        if level > 0:
            lo, hi = band(hist, level)
            model.units[cid] = Unit(cid, layer_of(cid, None, natures), level, direction(hist), hist, lo, hi)
    inc_hist = [income[k] for k in keys]
    model.other_income = weighted_level(inc_hist)
    if daily["revenu"]:
        total, acc = sum(a for _, a in daily["revenu"]), 0
        for d, a in sorted(daily["revenu"], key=lambda x: x[0].day):
            acc += a
            if acc >= 0.8 * total:
                model.other_income_day = d.day
                break
    model.other_income_direction = direction(inc_hist)
    model.profiles = {n: learn_profile(daily[n], len(keys)) for n in (*NATURES, "revenu")}
    _learn_recent(db, model, today, account_ids)
    return model


def _learn_recent(db: Session, model: Model, today: date, account_ids: list[int] | None) -> None:
    """Vendeurs habituels (3 derniers mois) et dépenses déjà faites ce mois-ci, par catégorie."""
    lo = today - timedelta(days=HABIT_WINDOW_DAYS)
    q = select(Transaction.booked_at, Transaction.amount_cents, Transaction.category_id, Transaction.merchant_id, Merchant.name).join(
        Merchant, Transaction.merchant_id == Merchant.id
    ).where(
        Transaction.booked_at >= lo, Transaction.booked_at <= today, Transaction.amount_cents < 0,
        Transaction.counted.is_(True), Transaction.is_transfer.is_(False), Transaction.recurring_id.is_(None),
    )
    if account_ids:
        q = q.where(Transaction.account_id.in_(account_ids))
    visits: dict[int, list[tuple[date, int]]] = defaultdict(list)
    cats: dict[int, dict[int | None, int]] = defaultdict(lambda: defaultdict(int))
    names: dict[int, str] = {}
    for r in db.execute(q).all():
        visits[r.merchant_id].append((r.booked_at, -r.amount_cents))
        cats[r.merchant_id][r.category_id] += 1
        names[r.merchant_id] = r.name
    for mid, pts in visits.items():
        cid = max(cats[mid].items(), key=lambda kv: kv[1])[0]
        if cid not in model.units or model.units[cid].layer == "fixe" or model.units[cid].occasional is not None:
            continue
        h = learn_habit(mid, names[mid], pts, today)
        if h is not None:
            model.habits.setdefault(cid, []).append(h)

    q = select(Transaction.category_id, Transaction.amount_cents).where(
        Transaction.booked_at >= today.replace(day=1), Transaction.booked_at <= today, Transaction.amount_cents < 0,
        Transaction.counted.is_(True), Transaction.is_transfer.is_(False), Transaction.recurring_id.is_(None),
    )
    if account_ids:
        q = q.where(Transaction.account_id.in_(account_ids))
    spent: dict[int | None, int] = defaultdict(int)
    for r in db.execute(q).all():
        spent[r.category_id] -= r.amount_cents
    # Paiements par carte pas encore comptabilisés : déjà dépensés eux aussi.
    pq = select(PendingTransaction.category_id, PendingTransaction.amount_cents).where(PendingTransaction.amount_cents < 0)
    if account_ids:
        pq = pq.where(PendingTransaction.account_id.in_(account_ids))
    for r in db.execute(pq).all():
        spent[r.category_id] -= r.amount_cents
    model.spent_month = dict(spent)


def _unit_days(model: Model, u: Unit, monthly: float, today: date, end: date) -> dict[date, float]:
    """Dépense attendue chaque jour (de demain à end) pour une catégorie : vendeurs habituels + rythme de la couche ;
    pour la fin du mois en cours, ce qui reste d'après ce qui est déjà dépensé."""
    tomorrow = today + timedelta(days=1)
    if end < tomorrow or monthly <= 0:
        return {}
    if u.occasional is not None:
        # De temps en temps : le montant habituel d'un coup, à chaque date attendue (ramené au scénario).
        occ, scale = u.occasional, monthly / u.monthly if u.monthly else 1.0
        days: dict[date, float] = {}
        d = occ.next_date
        while d <= end:
            if d >= tomorrow:
                days[d] = occ.amount * scale
            d += timedelta(days=occ.every_days)
        return days
    profile = model.profiles.get(u.layer, Profile())
    habits = model.habits.get(u.category_id, [])
    days = unit_expected(monthly, habits, profile, tomorrow, end)
    month_end = month_bounds(today)[1]
    rest_by_rhythm = sum(v for d, v in days.items() if d <= month_end)
    if rest_by_rhythm > 0:
        so_far = sum(unit_expected(monthly, habits, profile, today.replace(day=1), today).values())
        rest = rest_of_month(rest_by_rhythm, monthly, model.spent_month.get(u.category_id, 0), so_far)
        factor = rest / rest_by_rhythm
        for d in days:
            if d <= month_end:
                days[d] *= factor
    return days


@dataclass
class Scenario:
    plaisir_pct: int = 100
    apply_budgets: bool = False
    targets: dict[int, int] = field(default_factory=dict)  # objectifs mensuels par catégorie (centimes)
    extra_saving_cents: int = 0

    @property
    def active(self) -> bool:
        return self.plaisir_pct != 100 or self.apply_budgets or bool(self.targets) or self.extra_saving_cents > 0


def scenario_units(db: Session, model: Model, sc: Scenario) -> dict[int | None, float]:
    """Montants mensuels attendus par catégorie après budgets / objectifs (plafonds) et curseur des plaisirs."""
    parents = dict(db.execute(select(Category.id, Category.parent_id)).all())
    caps: dict[int, float] = {}
    if sc.apply_budgets:
        caps.update({b.category_id: b.monthly_amount_cents for b in db.scalars(select(Budget))})
    caps.update({cid: v for cid, v in sc.targets.items()})
    units = apply_caps({cid: float(u.monthly) for cid, u in model.units.items()}, parents, caps)
    return {cid: v * (sc.plaisir_pct / 100 if model.units[cid].layer == "plaisir" else 1) for cid, v in units.items()}


def _layer_totals(model: Model, units: dict[int | None, float]) -> dict[str, float]:
    totals = {n: 0.0 for n in NATURES}
    for cid, v in units.items():
        totals[model.units[cid].layer] += v
    return totals


# --- Simulation jour par jour -------------------------------------------------------------------


def _start(db: Session, ids: list[int]) -> int:
    total = 0
    for aid in ids:
        bal, _ = current_balance(db, aid)
        total += bal or 0
    return total


def _usual_day(db: Session, s: RecurringSeries) -> int | None:
    """Jour du mois prudent pour une échéance mensuelle (ou plus espacée) : un revenu au plus tard de ses dates
    habituelles (salaire versé entre le 25 et le 28 → le 28), une dépense au plus tôt. None : pas d'ajustement."""
    f = FREQUENCIES.get(s.frequency)
    if f is None or f.months is None:
        return None
    days = [d.day for d in db.scalars(
        select(Transaction.booked_at).where(Transaction.recurring_id == s.id).order_by(Transaction.booked_at.desc()).limit(6)
    )]
    if len(days) < 2 or max(days) - min(days) > 12:  # rien à comparer, ou dates à cheval sur deux mois (31 / 2)
        return None
    return max(days) if s.expected_amount_cents > 0 else min(days)


def _scheduled(db: Session, ids: list[int], lo: date, hi: date, names: dict[int, str]) -> list[dict]:
    """Échéances connues entre lo et hi : récurrents des comptes choisis, à leur date prudente."""
    events = []
    raw = get_meta(db, "payday")
    payday = int(raw) if raw and raw.isdigit() else None  # jour de paie réglé à la main (Récurrents)
    for s in _active_series(db):
        if s.account_id not in ids:
            continue
        if s.end_date is not None and s.end_date < lo:
            continue
        is_pay = payday is not None and s.expected_amount_cents >= 20000 and not s.is_transfer and s.frequency == "mensuel"
        usual = payday if is_pay else _usual_day(db, s)
        last_ok = min(hi, s.end_date) if s.end_date is not None else hi
        for d in occurrences(s.next_expected_date, s.frequency, lo, last_ok):
            late = s.next_expected_date is not None and d == lo and s.next_expected_date < lo
            if usual is not None:
                moved = d.replace(day=min(usual, calendar.monthrange(d.year, d.month)[1]))
                d = moved if is_pay else max(d, moved) if s.expected_amount_cents > 0 else min(d, moved)
                d = max(d, lo)
                if d > hi:
                    continue
            events.append({
                "date": d, "label": s.label, "amount_cents": s.expected_amount_cents,
                "kind": "virement" if s.is_transfer else ("revenu" if s.expected_amount_cents > 0 else "depense"),
                "series_id": s.id, "category_id": s.category_id, "account_name": names.get(s.account_id), "status": s.status,
                "late": late,
            })
    return events


def _other_income_events(db: Session, model: Model, today: date, end: date, ids: list[int]) -> list[dict]:
    """Revenus habituels hors récurrents (remboursements, primes…) : leur tendance mensuelle, versée en une fois au jour
    du mois où ils arrivent d'habitude (au plus tard). Ce mois-ci : seulement ce qui n'est pas déjà arrivé."""
    if model.other_income <= 0:
        return []
    q = select(Transaction.amount_cents).where(
        Transaction.booked_at >= today.replace(day=1), Transaction.booked_at <= today, Transaction.amount_cents > 0,
        Transaction.counted.is_(True), Transaction.is_transfer.is_(False), Transaction.recurring_id.is_(None),
    )
    if ids:
        q = q.where(Transaction.account_id.in_(ids))
    received = sum(db.scalars(q))
    events = []
    m = today.replace(day=1)
    while m <= end:
        d = m.replace(day=min(model.other_income_day, calendar.monthrange(m.year, m.month)[1]))
        amount = model.other_income - (received if m.month == today.month and m.year == today.year else 0)
        if today < d <= end and amount > 0:
            events.append({"date": d, "label": "Autres revenus habituels", "amount_cents": amount, "kind": "revenu", "series_id": None,
                           "category_id": None, "account_name": None, "status": "tendance", "late": False})
        m = _shift_month(m, 1)
    return events


def _simulate(db: Session, today: date, end: date, ids: list[int], model: Model, sc: Scenario, names: dict[int, str]) -> dict:
    """Jour par jour, de today à end : composantes du solde et solde final, pour le scénario et sans scénario."""
    events = []
    for p in db.scalars(select(PendingTransaction).where(PendingTransaction.account_id.in_(ids))) if ids else []:
        events.append({"date": today, "label": (p.merchant or p.raw_label.split(" | ")[0])[:60], "amount_cents": p.amount_cents,
                       "kind": "a_venir", "series_id": None, "category_id": p.category_id, "account_name": names.get(p.account_id),
                       "status": None, "late": False})
    events += _scheduled(db, ids, today, end, names)
    events += _other_income_events(db, model, today, end, ids)
    # Épargne en plus (scénario) : un virement le 1er de chaque mois à venir.
    if sc.extra_saving_cents > 0:
        m = _shift_month(today, 1)
        while m <= end:
            events.append({"date": m, "label": "Épargne en plus (scénario)", "amount_cents": -sc.extra_saving_cents, "kind": "virement",
                           "series_id": None, "category_id": None, "account_name": None, "status": "scenario", "late": False})
            m = _shift_month(m, 1)
    events.sort(key=lambda e: (e["date"], e["amount_cents"]))

    units_scen = scenario_units(db, model, sc)
    scen = _layer_totals(model, units_scen)
    base = _layer_totals(model, {cid: float(u.monthly) for cid, u in model.units.items()})

    # Chaque catégorie jour par jour (avec le scénario, et sans), puis par couche ; fourchette (mois bons / mauvais).
    exp: dict[str, dict[date, float]] = {n: defaultdict(float) for n in NATURES}
    exp_base: dict[str, dict[date, float]] = {n: defaultdict(float) for n in NATURES}
    exp_lo: dict[str, dict[date, float]] = {n: defaultdict(float) for n in NATURES}
    exp_hi: dict[str, dict[date, float]] = {n: defaultdict(float) for n in NATURES}
    unit_totals: dict[int | None, tuple[float, float]] = {}
    for cid, u in model.units.items():
        days_s = _unit_days(model, u, units_scen[cid], today, end)
        days_b = days_s if units_scen[cid] == u.monthly else _unit_days(model, u, u.monthly, today, end)
        for d, v in days_s.items():
            exp[u.layer][d] += v
            exp_lo[u.layer][d] += v * u.lo
            exp_hi[u.layer][d] += v * u.hi
        for d, v in days_b.items():
            exp_base[u.layer][d] += v
        unit_totals[cid] = (sum(days_s.values()), sum(days_b.values()))

    by_day: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in events:
        k = {"revenu": "income", "depense": "fixed", "virement": "transfer"}.get(e["kind"])
        if e["kind"] == "a_venir":
            k = "income" if e["amount_cents"] > 0 else "essential_pending"
        if e["status"] == "scenario":
            k = "extra"
        by_day[e["date"]][k] += e["amount_cents"]

    start = _start(db, ids)
    days = []
    c = defaultdict(float)  # cumuls
    d = today
    while d <= end:
        ev = by_day.get(d, {})
        c["income"] += ev.get("income", 0)
        c["fixed_events"] += -ev.get("fixed", 0)
        c["fixe_var"] += exp["fixe"].get(d, 0)
        c["pending"] += -ev.get("essential_pending", 0)
        c["essentiel"] += exp["essentiel"].get(d, 0)
        c["plaisir"] += exp["plaisir"].get(d, 0)
        for n in ("essentiel", "plaisir"):
            c[f"{n}_lo"] += exp_lo[n].get(d, 0)
            c[f"{n}_hi"] += exp_hi[n].get(d, 0)
        c["transfer"] += ev.get("transfer", 0)
        c["extra"] += ev.get("extra", 0)
        c["base_var"] += sum(exp_base[n].get(d, 0) for n in NATURES)
        fixed = c["fixed_events"] + c["fixe_var"]
        essentials = c["pending"] + c["essentiel"]
        socle = start + c["income"] - fixed + c["transfer"] + c["extra"]
        after_ess = socle - essentials
        balance = after_ess - c["plaisir"]
        # Sans scénario : mêmes échéances, tendances brutes, pas d'épargne en plus.
        baseline = start + c["income"] - c["fixed_events"] - c["pending"] - c["base_var"] + c["transfer"]
        days.append({
            "date": d, "income": c["income"], "fixed": fixed, "fixed_events": c["fixed_events"], "essentiel": essentials,
            "plaisir": c["plaisir"], "transfer": c["transfer"] + c["extra"],
            "essentiel_lo": c["pending"] + c["essentiel_lo"], "essentiel_hi": c["pending"] + c["essentiel_hi"],
            "plaisir_lo": c["plaisir_lo"], "plaisir_hi": c["plaisir_hi"],
            "socle": socle, "after_essentials": after_ess, "balance": balance, "baseline": baseline,
        })
        d += timedelta(days=1)
    return {"start": start, "events": events, "days": days, "layers_monthly": scen, "layers_monthly_base": base, "unit_totals": unit_totals}


def _category_forecast(db: Session, model: Model, sc: Scenario, sim: dict) -> list[dict]:
    """Ce qui est prévu d'ici l'horizon pour chaque catégorie sans date fixe (part de sa couche), avec et sans scénario."""
    scen = scenario_units(db, model, sc)
    out = []
    for cid, u in model.units.items():
        amount, base = sim["unit_totals"].get(cid, (0.0, 0.0))
        out.append({"category_id": cid, "layer": u.layer, "monthly_cents": u.monthly, "scenario_monthly_cents": round(scen[cid]),
                    "amount_cents": round(amount), "base_amount_cents": round(base), "direction": u.direction,
                    "spent_month_cents": model.spent_month.get(cid, 0),
                    "occasional": {"amount_cents": u.occasional.amount, "every_days": u.occasional.every_days,
                                   "next_date": u.occasional.next_date, "yearly_cents": round(u.occasional.yearly),
                                   "count": u.occasional.count} if u.occasional else None,
                    "habits": [{"merchant": h.label, "amount_cents": h.amount, "per_week": round(h.per_week, 2),
                                "days": [i for i, w in sorted(enumerate(h.weekday), key=lambda x: -x[1])[:2] if w >= 0.25]}
                               for h in model.habits.get(cid, [])]})
    out.sort(key=lambda x: -x["base_amount_cents"])
    return out


# --- Présentation du modèle (panneau scénario) --------------------------------------------------


def model_view(db: Session, model: Model, sc: Scenario) -> dict:
    """Catégories regroupées par catégorie principale : tendance, montant du scénario, budget, sens."""
    parents = dict(db.execute(select(Category.id, Category.parent_id)).all())
    budgets = {b.category_id: b.monthly_amount_cents for b in db.scalars(select(Budget))}
    scen = scenario_units(db, model, sc)
    groups: dict[int | None, dict] = {}
    for cid, u in model.units.items():
        top = (parents.get(cid) or cid) if cid is not None else None
        g = groups.setdefault(top, {"category_id": top, "trend_cents": 0, "scenario_cents": 0, "budget_cents": budgets.get(top) if top else None,
                                    "target_cents": sc.targets.get(top) if top else None, "layers": set(), "children": []})
        g["trend_cents"] += u.monthly
        g["scenario_cents"] += round(scen[cid])
        g["layers"].add(u.layer)
        g["children"].append({
            "category_id": cid, "layer": u.layer, "trend_cents": u.monthly, "scenario_cents": round(scen[cid]),
            "direction": u.direction, "budget_cents": budgets.get(cid) if cid is not None and cid != top else None,
            "target_cents": sc.targets.get(cid) if cid is not None and cid != top else None,
            "history": u.history,
        })
    out = []
    order = {"fixe": 0, "essentiel": 1, "plaisir": 2}
    for g in groups.values():
        g["children"].sort(key=lambda c: -c["trend_cents"])
        g["layers"] = sorted(g["layers"], key=lambda n: order[n])
        out.append(g)
    out.sort(key=lambda g: (order[g["layers"][0]], -g["trend_cents"]))
    totals = _layer_totals(model, {cid: float(u.monthly) for cid, u in model.units.items()})
    return {
        "months_used": model.months_used,
        "groups": out,
        "layers": {n: {"trend_cents": round(totals[n]), "scenario_cents": round(_layer_totals(model, scen)[n])} for n in NATURES},
        "other_income_cents": model.other_income,
        "other_income_direction": model.other_income_direction,
    }


# --- Prévision de trésorerie (jour par jour) ----------------------------------------------------


def forecast(db: Session, today: date, horizon: date, account_ids: list[int] | None = None, sc: Scenario | None = None) -> dict:
    sc = sc or Scenario()
    ids = account_ids or default_accounts(db)
    names = dict(db.execute(select(Account.id, Account.name)).all())
    model = build_model(db, today, ids)
    sim = _simulate(db, today, horizon, ids, model, sc, names)
    days = sim["days"]
    last = days[-1]
    low = min(days, key=lambda x: x["balance"])
    n_days = (horizon - today).days
    variable = last["essentiel"] + last["plaisir"] + (last["fixed"] - last["fixed_events"])
    return {
        "today": today,
        "horizon": horizon,
        "account_ids": ids,
        "accounts": [names.get(i) for i in ids],
        "start_balance_cents": sim["start"],
        "end_balance_cents": round(last["balance"]),
        "baseline_end_cents": round(last["baseline"]),
        "lowest": {"date": low["date"], "balance_cents": round(low["balance"])},
        "totals": {
            "income_cents": round(last["income"]), "fixe_cents": round(last["fixed"]), "essentiel_cents": round(last["essentiel"]),
            "plaisir_cents": round(last["plaisir"]), "epargne_cents": round(-last["transfer"]),
            # Détail des charges fixes : échéances datées (dont à confirmer / en retard) + estimation sans date fixe.
            "fixe_scheduled_cents": round(last["fixed_events"]),
            "fixe_unconfirmed_cents": -sum(e["amount_cents"] for e in sim["events"] if e["kind"] == "depense" and e["status"] == "suggere"),
            "fixe_late_cents": -sum(e["amount_cents"] for e in sim["events"] if e["kind"] == "depense" and e["late"]),
            "fixe_estimated_cents": round(last["fixed"] - last["fixed_events"]),
        },
        # Champs gardés pour la carte d'accueil.
        "income_cents": round(last["income"]),
        "fixed_out_cents": -round(last["fixed"]),
        "variable_total_cents": round(variable),
        "daily_variable_cents": round(variable / n_days) if n_days else 0,
        "events": sim["events"],
        "categories": _category_forecast(db, model, sc, sim),
        "points": [
            {"date": x["date"], "socle_cents": round(x["socle"]), "after_essentials_cents": round(x["after_essentials"]),
             "balance_cents": round(x["balance"]), "baseline_cents": round(x["baseline"]),
             # Cumuls depuis aujourd'hui (positifs), pour recalculer les courbes quand on retire une couche.
             "income_cum": round(x["income"]), "fixed_cum": round(x["fixed"]), "essentiel_cum": round(x["essentiel"]),
             "plaisir_cum": round(x["plaisir"]), "transfer_cum": round(x["transfer"]),
             # Fourchette : dépenses courantes d'un mois « bon » (lo) / « mauvais » (hi).
             "essentiel_lo_cum": round(x["essentiel_lo"]), "essentiel_hi_cum": round(x["essentiel_hi"]),
             "plaisir_lo_cum": round(x["plaisir_lo"]), "plaisir_hi_cum": round(x["plaisir_hi"])}
            for x in days
        ],
        "model": model_view(db, model, sc),
        "scenario": {"plaisir_pct": sc.plaisir_pct, "apply_budgets": sc.apply_budgets, "targets": sc.targets,
                     "extra_saving_cents": sc.extra_saving_cents, "active": sc.active},
    }


# --- Projection (mois par mois) -----------------------------------------------------------------


def _others_net_worth(db: Session, ids: list[int]) -> int:
    """Patrimoine hors comptes simulés : soldes des autres comptes actifs comptés dans le patrimoine."""
    total = 0
    for a in db.scalars(select(Account).where(Account.is_archived.is_(False), Account.include_in_net_worth.is_(True))):
        if a.id not in ids:
            total += current_balance(db, a.id)[0] or 0
    return total


def projection(db: Session, today: date, months: int, account_ids: list[int] | None = None, sc: Scenario | None = None, rate: float = 2.0) -> dict:
    """Mois par mois (le mois en cours : ce qui reste à venir), même moteur que la trésorerie."""
    sc = sc or Scenario()
    ids = account_ids or default_accounts(db)
    names = dict(db.execute(select(Account.id, Account.name)).all())
    model = build_model(db, today, ids)
    end = month_bounds(_shift_month(today, months - 1))[1]
    sim = _simulate(db, today, end, ids, model, sc, names)
    out, prev = [], None
    others = float(_others_net_worth(db, ids))
    for x in sim["days"]:
        if x["date"] != month_bounds(x["date"])[1]:
            continue
        p = prev or {"income": 0, "fixed": 0, "essentiel": 0, "plaisir": 0, "transfer": 0, "balance": sim["start"], "baseline": sim["start"]}
        row = {
            "month": x["date"].strftime("%Y-%m"),
            "partial": x["date"].month == today.month and x["date"].year == today.year,
            "income_cents": round(x["income"] - p["income"]),
            "fixe_cents": round(x["fixed"] - p["fixed"]),
            "essentiel_cents": round(x["essentiel"] - p["essentiel"]),
            "plaisir_cents": round(x["plaisir"] - p["plaisir"]),
            "epargne_cents": round(-(x["transfer"] - p["transfer"])),
            "end_balance_cents": round(x["balance"]),
            "baseline_end_cents": round(x["baseline"]),
        }
        row["net_cents"] = round(x["balance"] - p["balance"])
        # Patrimoine : comptes du quotidien (simulés) + le reste (épargne, placements…), qui reçoit l'épargne du mois
        # et rapporte `rate` % par an.
        others = others * (1 + rate / 100 / 12) + row["epargne_cents"]
        row["net_worth_cents"] = round(x["balance"] + others)
        out.append(row)
        prev = x
    full = out[1:] or out
    lowest = min(out, key=lambda m: m["end_balance_cents"]) if out else None
    return {
        "today": today,
        "account_ids": ids,
        "accounts": [names.get(i) for i in ids],
        "start_balance_cents": sim["start"],
        "end_balance_cents": out[-1]["end_balance_cents"] if out else sim["start"],
        "baseline_end_cents": out[-1]["baseline_end_cents"] if out else sim["start"],
        "net_worth_start_cents": sim["start"] + _others_net_worth(db, ids),
        "rate": rate,
        "avg_net_cents": round(sum(m["net_cents"] for m in full) / len(full)) if full else 0,
        "avg_saving_cents": round(sum(m["epargne_cents"] for m in full) / len(full)) if full else 0,
        "lowest": {"month": lowest["month"], "balance_cents": lowest["end_balance_cents"]} if lowest else None,
        "first_negative_month": next((m["month"] for m in out if m["end_balance_cents"] < 0), None),
        "months": out,
        "model": model_view(db, model, sc),
        "scenario": {"plaisir_pct": sc.plaisir_pct, "apply_budgets": sc.apply_budgets, "targets": sc.targets,
                     "extra_saving_cents": sc.extra_saving_cents, "active": sc.active},
    }


# --- Budgets ------------------------------------------------------------------------------------


def budgets_overview(db: Session, month: date, today: date) -> dict:
    start, end = month_bounds(month)
    parents = dict(db.execute(select(Category.id, Category.parent_id)).all())
    budgets = db.scalars(select(Budget)).all()
    rows = _expenses(db, start, end)
    current = start <= today <= end
    days = (end - start).days + 1
    elapsed = (today - start).days + 1 if current else days
    remaining_days = days - elapsed if current else 0

    raw_global = get_meta(db, "global_budget_cents")
    global_budget = int(raw_global) if raw_global and raw_global.isdigit() and int(raw_global) > 0 else None
    model = build_model(db, today, None) if budgets or current or global_budget else Model()
    series = _active_series(db)
    # Prélèvements récurrents encore attendus ce mois-ci (après aujourd'hui), par catégorie.
    upcoming: dict[int | None, int] = defaultdict(int)
    recurring_monthly: dict[int | None, int] = defaultdict(int)
    for s in series:
        if s.expected_amount_cents < 0 and not s.is_transfer:
            recurring_monthly[s.category_id] -= monthly_cost(s.expected_amount_cents, s.frequency)
            if current:
                for _ in occurrences(s.next_expected_date, s.frequency, today + timedelta(days=1), min(end, s.end_date or end)):
                    upcoming[s.category_id] -= s.expected_amount_cents

    items = []
    for b in budgets:
        fam = _family(parents, b.category_id)
        mine = [r for r in rows if r.category_id in fam]
        spent = -sum(r.amount_cents for r in mine)
        recurring_spent = -sum(r.amount_cents for r in mine if r.recurring_id is not None)
        expected_recurring = sum(v for cid, v in upcoming.items() if cid in fam)
        # Reste du mois : pour chaque catégorie de la famille, son habitude moins ce qui est déjà dépensé (voir _unit_days).
        expected_variable = 0.0
        trend = sum(v for cid, v in recurring_monthly.items() if cid in fam)
        for cid, u in model.units.items():
            if cid in fam:
                trend += u.monthly
                if current and remaining_days > 0:
                    expected_variable += sum(_unit_days(model, u, u.monthly, today, end).values())
        projected = spent + expected_recurring + round(expected_variable)
        pct = spent / b.monthly_amount_cents if b.monthly_amount_cents > 0 else 0
        pace = round(b.monthly_amount_cents * elapsed / days) if current else b.monthly_amount_cents
        if spent > b.monthly_amount_cents:
            level = "depasse"
        elif pct * 100 >= b.alert_threshold_pct or (current and projected > b.monthly_amount_cents):
            level = "alerte"
        else:
            level = "ok"
        items.append({
            "category_id": b.category_id,
            "budget_cents": b.monthly_amount_cents,
            "alert_threshold_pct": b.alert_threshold_pct,
            "spent_cents": spent,
            "recurring_spent_cents": recurring_spent,
            "expected_recurring_cents": expected_recurring,
            "projected_cents": projected if current else spent,
            "trend_cents": round(trend),
            "pace_cents": pace,
            "remaining_cents": b.monthly_amount_cents - spent,
            "level": level,
        })
    order = {"depasse": 0, "alerte": 1, "ok": 2}
    items.sort(key=lambda i: (order[i["level"]], -(i["spent_cents"] / max(i["budget_cents"], 1))))

    budgeted = {b.category_id for b in budgets}
    tops = [i for i in items if parents.get(i["category_id"]) not in budgeted]

    # Budget global : toutes les dépenses du mois (hors virements entre mes comptes).
    glob = None
    if global_budget:
        spent_all = -sum(r.amount_cents for r in rows)
        rest = sum(upcoming.values()) + round(sum(sum(_unit_days(model, u, u.monthly, today, end).values()) for u in model.units.values())) \
            if current and remaining_days > 0 else 0
        projected_all = spent_all + rest
        level = "depasse" if spent_all > global_budget else "alerte" if spent_all >= 0.8 * global_budget or (current and projected_all > global_budget) else "ok"
        glob = {
            "budget_cents": global_budget, "spent_cents": spent_all, "projected_cents": projected_all if current else spent_all,
            "trend_cents": round(sum(recurring_monthly.values()) + sum(u.monthly for u in model.units.values())),
            "pace_cents": round(global_budget * elapsed / days) if current else global_budget,
            "remaining_cents": global_budget - spent_all, "level": level,
        }
    return {
        "global": glob,
        "month": start.strftime("%Y-%m"),
        "is_current": current,
        "days_in_month": days,
        "elapsed_days": elapsed,
        "remaining_days": remaining_days,
        "total_budget_cents": sum(i["budget_cents"] for i in tops),
        "total_spent_cents": sum(i["spent_cents"] for i in tops),
        "total_projected_cents": sum(i["projected_cents"] for i in tops),
        "items": items,
        "suggestions": budget_suggestions(db, model, parents, budgeted, recurring_monthly),
    }


def budget_suggestions(db: Session, model: Model, parents: dict, budgeted: set[int], recurring_monthly: dict) -> list[dict]:
    """Catégories de dépense principales sans budget : leur tendance (récurrents compris), arrondie au-dessus."""
    kinds = dict(db.execute(select(Category.id, Category.kind)).all())
    per_top: dict[int, int] = defaultdict(int)
    for cid, u in model.units.items():
        if cid is not None:
            per_top[parents.get(cid) or cid] += u.monthly
    for cid, v in recurring_monthly.items():
        if cid is not None:
            per_top[parents.get(cid) or cid] += v
    out = []
    for cid, avg in per_top.items():
        if cid in budgeted or kinds.get(cid) != "depense" or avg < 1000:
            continue
        step = 1000 if avg < 20000 else 5000  # arrondi à 10 € (ou 50 € au-delà de 200 €)
        out.append({"category_id": cid, "average_cents": round(avg), "suggested_cents": math.ceil(avg / step) * step})
    return sorted(out, key=lambda s: -s["average_cents"])
