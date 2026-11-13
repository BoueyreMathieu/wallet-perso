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
from app.models import Account, Budget, Category, PendingTransaction, RecurringSeries, Transaction
from app.recurrence import FREQUENCIES, monthly_cost, occurrences
from app.seed import resolve_paths
from app.services.balances import current_balance
from app.services.recurring import ACTIVE_STATUSES
from app.trends import MAX_MONTHS, Profile, apply_caps, direction, expected_between, learn_profile, weighted_level

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


@dataclass
class Model:
    units: dict[int | None, Unit] = field(default_factory=dict)
    profiles: dict[str, Profile] = field(default_factory=dict)
    other_income: int = 0
    other_income_direction: str = "stable"
    other_income_day: int = 28  # jour du mois où ils sont arrivés pour 80 % (au plus tard)
    months_used: int = 0


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
    q = select(Transaction.booked_at, Transaction.amount_cents, Transaction.category_id).where(
        Transaction.booked_at >= months[0], Transaction.booked_at <= last,
        Transaction.counted.is_(True), Transaction.is_transfer.is_(False), Transaction.recurring_id.is_(None),
    )
    if account_ids:
        q = q.where(Transaction.account_id.in_(account_ids))
    for r in db.execute(q).all():
        k = r.booked_at.strftime("%Y-%m")
        if r.amount_cents > 0:
            income[k] += r.amount_cents
            daily["revenu"].append((r.booked_at, r.amount_cents))
        else:
            per_unit[r.category_id][k] -= r.amount_cents
            daily[layer_of(r.category_id, None, natures)].append((r.booked_at, -r.amount_cents))

    for cid, by_month in per_unit.items():
        hist = [by_month[k] for k in keys]
        while hist and hist[0] == 0:  # mois avant la première dépense de la catégorie : pas des mois « à 0 € »
            hist.pop(0)
        level = weighted_level(hist)
        if level > 0:
            model.units[cid] = Unit(cid, layer_of(cid, None, natures), level, direction(hist), hist)
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
    return model


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
    for s in _active_series(db):
        if s.account_id not in ids:
            continue
        usual = _usual_day(db, s)
        for d in occurrences(s.next_expected_date, s.frequency, lo, hi):
            late = s.next_expected_date is not None and d == lo and s.next_expected_date < lo
            if usual is not None:
                moved = d.replace(day=min(usual, calendar.monthrange(d.year, d.month)[1]))
                d = max(d, moved) if s.expected_amount_cents > 0 else min(d, moved)
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

    tomorrow = today + timedelta(days=1)
    scen = _layer_totals(model, scenario_units(db, model, sc))
    base = _layer_totals(model, {cid: float(u.monthly) for cid, u in model.units.items()})

    def spread(monthly: float, layer: str) -> dict[date, float]:
        return expected_between(monthly, tomorrow, end, model.profiles.get(layer, Profile())) if end >= tomorrow and monthly > 0 else {}

    exp = {n: spread(scen[n], n) for n in NATURES}
    exp_base = {n: spread(base[n], n) for n in NATURES}

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
            "socle": socle, "after_essentials": after_ess, "balance": balance, "baseline": baseline,
        })
        d += timedelta(days=1)
    return {"start": start, "events": events, "days": days, "layers_monthly": scen, "layers_monthly_base": base,
            "horizon_layers": {n: sum(exp[n].values()) for n in NATURES}, "horizon_layers_base": {n: sum(exp_base[n].values()) for n in NATURES}}


def _category_forecast(db: Session, model: Model, sc: Scenario, sim: dict) -> list[dict]:
    """Ce qui est prévu d'ici l'horizon pour chaque catégorie sans date fixe (part de sa couche), avec et sans scénario."""
    scen = scenario_units(db, model, sc)
    out = []
    for cid, u in model.units.items():
        layer_scen, layer_base = sim["layers_monthly"][u.layer], sim["layers_monthly_base"][u.layer]
        amount = sim["horizon_layers"][u.layer] * scen[cid] / layer_scen if layer_scen else 0
        base = sim["horizon_layers_base"][u.layer] * u.monthly / layer_base if layer_base else 0
        out.append({"category_id": cid, "layer": u.layer, "monthly_cents": u.monthly, "scenario_monthly_cents": round(scen[cid]),
                    "amount_cents": round(amount), "base_amount_cents": round(base), "direction": u.direction})
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
             "plaisir_cum": round(x["plaisir"]), "transfer_cum": round(x["transfer"])}
            for x in days
        ],
        "model": model_view(db, model, sc),
        "scenario": {"plaisir_pct": sc.plaisir_pct, "apply_budgets": sc.apply_budgets, "targets": sc.targets,
                     "extra_saving_cents": sc.extra_saving_cents, "active": sc.active},
    }


# --- Projection (mois par mois) -----------------------------------------------------------------


def projection(db: Session, today: date, months: int, account_ids: list[int] | None = None, sc: Scenario | None = None) -> dict:
    """Mois par mois (le mois en cours : ce qui reste à venir), même moteur que la trésorerie."""
    sc = sc or Scenario()
    ids = account_ids or default_accounts(db)
    names = dict(db.execute(select(Account.id, Account.name)).all())
    model = build_model(db, today, ids)
    end = month_bounds(_shift_month(today, months - 1))[1]
    sim = _simulate(db, today, end, ids, model, sc, names)
    out, prev = [], None
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

    model = build_model(db, today, None) if budgets or current else Model()
    series = _active_series(db)
    # Prélèvements récurrents encore attendus ce mois-ci (après aujourd'hui), par catégorie.
    upcoming: dict[int | None, int] = defaultdict(int)
    recurring_monthly: dict[int | None, int] = defaultdict(int)
    for s in series:
        if s.expected_amount_cents < 0 and not s.is_transfer:
            recurring_monthly[s.category_id] -= monthly_cost(s.expected_amount_cents, s.frequency)
            if current:
                for _ in occurrences(s.next_expected_date, s.frequency, today + timedelta(days=1), end):
                    upcoming[s.category_id] -= s.expected_amount_cents

    tomorrow = today + timedelta(days=1)
    items = []
    for b in budgets:
        fam = _family(parents, b.category_id)
        mine = [r for r in rows if r.category_id in fam]
        spent = -sum(r.amount_cents for r in mine)
        recurring_spent = -sum(r.amount_cents for r in mine if r.recurring_id is not None)
        expected_recurring = sum(v for cid, v in upcoming.items() if cid in fam)
        # Reste du mois : la tendance de chaque catégorie de la famille, répartie selon tes habitudes.
        expected_variable = 0.0
        trend = sum(v for cid, v in recurring_monthly.items() if cid in fam)
        for cid, u in model.units.items():
            if cid in fam:
                trend += u.monthly
                if current and remaining_days > 0:
                    expected_variable += sum(expected_between(u.monthly, tomorrow, end, model.profiles.get(u.layer, Profile())).values())
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
    return {
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
