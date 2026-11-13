"""Détection des opérations récurrentes (cœur sans base de données, testable seul).

Entrée : les opérations d'un même vendeur, sur un même compte et dans un même sens (débit ou crédit).
Sortie : zéro, une ou plusieurs séries régulières (ex. chez un même vendeur : un abonnement à 9,99 € et des
achats ponctuels ; ou deux abonnements de montants différents).

Règles :
- d'abord toutes les opérations du groupe (gère les hausses de prix), sinon par paquets de montants proches ;
- intervalle médian dans la plage d'une fréquence (hebdomadaire… annuelle), 75 % des intervalles conformes
  (un mois sauté est toléré) ;
- montants stables : chacun à ±30 % de la médiane (±10 % en hebdomadaire, pour ne pas prendre la boulangerie) ;
- au moins 3 occurrences (2 pour semestriel / annuel, 5 pour hebdomadaire) ; quand le vendeur a aussi des achats
  ponctuels : paquets de montants proches (±25 %, 5 fois) ou exacts (3 fois) au rythme sans faille ;
- « active » si la dernière occurrence n'est pas trop ancienne (une période + une marge).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median


@dataclass(frozen=True)
class Frequency:
    code: str
    label: str
    days: float  # durée moyenne d'une période
    tolerance: int  # écart accepté sur un intervalle (jours)
    months: int | None  # pas en mois (None = en jours)
    min_occurrences: int
    per_year: float


FREQUENCIES: dict[str, Frequency] = {
    f.code: f
    for f in (
        Frequency("hebdomadaire", "chaque semaine", 7, 2, None, 5, 52.18),
        Frequency("mensuel", "chaque mois", 30.44, 6, 1, 3, 12),
        Frequency("bimestriel", "tous les 2 mois", 60.9, 8, 2, 3, 6),
        Frequency("trimestriel", "chaque trimestre", 91.3, 12, 3, 3, 4),
        Frequency("semestriel", "tous les 6 mois", 182.6, 20, 6, 2, 2),
        Frequency("annuel", "chaque année", 365.25, 25, 12, 2, 1),
    )
}


def add_months(d: date, n: int) -> date:
    idx = d.year * 12 + d.month - 1 + n
    y, m = idx // 12, idx % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def next_after(d: date, code: str) -> date:
    f = FREQUENCIES[code]
    return add_months(d, f.months) if f.months else d + timedelta(days=round(f.days))


def grace_days(code: str) -> int:
    """Retard toléré avant de considérer qu'une échéance ne viendra plus (résiliée)."""
    f = FREQUENCIES[code]
    return max(7, round(f.days * 0.5))


def occurrences(next_date: date | None, code: str, lo: date, hi: date) -> list[date]:
    """Échéances prévues entre lo et hi (inclus). Une échéance en retard (mais pas trop) est placée à lo."""
    if next_date is None or code not in FREQUENCIES:
        return []
    d = next_date
    out: list[date] = []
    if d < lo:
        if (lo - d).days > grace_days(code):
            # Trop en retard : on avance jusqu'à la prochaine échéance plausible.
            while d < lo:
                d = next_after(d, code)
        else:
            out.append(lo)
            d = next_after(d, code)
    while d <= hi:
        out.append(d)
        d = next_after(d, code)
    return out


def monthly_cost(amount_cents: int, code: str) -> int:
    """Équivalent mensuel d'un montant (ex. 120 €/an → 10 €/mois)."""
    f = FREQUENCIES.get(code)
    return round(amount_cents * f.per_year / 12) if f else amount_cents


@dataclass(frozen=True)
class Point:
    id: int
    day: date
    amount_cents: int  # signé


@dataclass
class Detection:
    frequency: str
    points: list[Point]
    active: bool
    expected_amount_cents: int
    previous_amount_cents: int | None = None
    price_changed_on: date | None = None
    ids: list[int] = field(default_factory=list)

    @property
    def first_date(self) -> date:
        return self.points[0].day

    @property
    def last_date(self) -> date:
        return self.points[-1].day

    @property
    def next_date(self) -> date:
        return next_after(self.last_date, self.frequency)


def _frequency_of(days: list[date], min_count: int = 0, strict: bool = False) -> str | None:
    intervals = [(b - a).days for a, b in zip(days, days[1:])]
    if not intervals or min(intervals) < 3:
        return None  # deux opérations le même jour ou presque : pas un rythme régulier
    med = median(intervals)
    for f in FREQUENCIES.values():
        if abs(med - f.days) > f.tolerance:
            continue
        if len(days) < max(f.min_occurrences, min_count):
            return None
        ok = sum(1 for i in intervals if abs(i - f.days) <= f.tolerance or abs(i - 2 * f.days) <= f.tolerance)
        return f.code if ok >= (len(intervals) if strict else 0.75 * len(intervals)) else None
    return None


def _stable(amounts: list[int], code: str, strict: bool = False, tol: float | None = None) -> bool:
    med = median(abs(a) for a in amounts)
    if med == 0:
        return False
    if strict:  # montant exact (au centime près ou à 1 %), comme un vrai abonnement
        return all(_same_price(a, amounts[-1]) for a in amounts)
    if tol is None:
        tol = 0.10 if code == "hebdomadaire" else 0.30
    return all(abs(abs(a) - med) <= tol * med + 50 for a in amounts)


def _same_price(a: int, b: int) -> bool:
    return abs(a - b) <= max(10, abs(b) // 100)  # 1 % ou 10 centimes


def _price_change(points: list[Point]) -> tuple[int | None, date | None]:
    """Ancien montant et date du changement, si le montant récent est stable et différent d'avant."""
    last = points[-1].amount_cents
    i = len(points) - 1
    while i > 0 and _same_price(points[i - 1].amount_cents, last):
        i -= 1
    if i == 0:
        return None, None
    before = points[i - 1].amount_cents
    # L'ancien prix doit lui-même avoir été stable (au moins 2 fois), sinon ce sont juste des montants variables.
    if i < 2 or not _same_price(points[i - 2].amount_cents, before):
        return None, None
    if abs(last - before) < max(50, abs(before) // 100):
        return None, None
    return before, points[i].day


def _build(points: list[Point], code: str, today: date) -> Detection:
    f = FREQUENCIES[code]
    last = points[-1]
    active = (today - last.day).days <= f.days + grace_days(code)
    prev, changed = _price_change(points)
    # Montant attendu : le dernier (après une hausse) ou la médiane des 3 derniers (montants variables).
    recent = [p.amount_cents for p in points[-3:]]
    expected = last.amount_cents if prev is not None or all(_same_price(a, last.amount_cents) for a in recent) else round(median(recent))
    return Detection(
        frequency=code,
        points=points,
        active=active,
        expected_amount_cents=expected,
        previous_amount_cents=prev,
        price_changed_on=changed,
        ids=[p.id for p in points],
    )


def _clusters(points: list[Point], ratio: float = 0.10, abs_tol: int = 100) -> list[list[Point]]:
    """Paquets de montants proches (par défaut ±10 % ou 1 €), triés par date."""
    by_amount = sorted(points, key=lambda p: abs(p.amount_cents))
    groups: list[list[Point]] = []
    for p in by_amount:
        if groups:
            ref = abs(groups[-1][0].amount_cents)
            if abs(p.amount_cents) <= ref * (1 + ratio) + abs_tol:
                groups[-1].append(p)
                continue
        groups.append([p])
    return [sorted(g, key=lambda p: (p.day, p.id)) for g in groups]


def _same_days(days: list[date], spread: int) -> bool:
    """Toujours vers le même jour du mois (à `spread` jours près, en tenant compte du passage d'un mois à l'autre)."""
    doms = sorted(d.day for d in days)
    if len(doms) < 2:
        return True
    gaps = [b - a for a, b in zip(doms, doms[1:])] + [doms[0] + 31 - doms[-1]]
    return 31 - max(gaps) <= spread


def detect(points: list[Point], today: date) -> list[Detection]:
    """Séries régulières parmi les opérations d'un même vendeur / compte / sens.

    1. Toutes les opérations ensemble (abonnement, facture, salaire : montants à ±30 %).
    2. Sinon, le vendeur a aussi des achats ponctuels : paquets de montants proches (±25 %) au rythme mensuel (ou plus)
       sans faille, toujours vers le même jour du mois, au moins 5 fois (facture variable chez un fournisseur…).
    3. Puis paquets de montants exacts au rythme sans faille, au moins 3 fois (abonnements)."""
    pts = sorted(points, key=lambda p: (p.day, p.id))
    if len(pts) < 2:
        return []
    code = _frequency_of([p.day for p in pts])
    if code and _stable([p.amount_cents for p in pts], code):
        return [_build(pts, code, today)]
    found: list[Detection] = []
    used: set[int] = set()
    if len(pts) >= 5:
        for group in _clusters(pts, ratio=0.35, abs_tol=200):
            if len(group) < 5 or len(group) == len(pts):
                continue
            code = _frequency_of([p.day for p in group], min_count=5, strict=True)
            months_based = code is not None and FREQUENCIES[code].months is not None
            if code and months_based and _same_days([p.day for p in group], 8) and _stable([p.amount_cents for p in group], code, tol=0.25):
                found.append(_build(group, code, today))
                used.update(p.id for p in group)
    rest = [p for p in pts if p.id not in used]
    for group in _clusters(rest):
        if len(group) < 2 or len(group) == len(pts):
            continue
        # Montants quasi identiques et rythme sans faille : un vrai abonnement, pas un hasard.
        code = _frequency_of([p.day for p in group], min_count=3, strict=True)
        if code and _stable([p.amount_cents for p in group], code, strict=True):
            found.append(_build(group, code, today))
    return found


def detect_regular_income(points: list[Point], today: date, min_amount: int = 20000) -> list[Detection]:
    """Revenus mensuels réguliers d'un compte, quels que soient libellé et catégorie (salaire au libellé changeant,
    jamais catégorisé…) : montants ≥ 200 €, à ±25 % les uns des autres, chaque mois sans faille, toujours vers le même
    jour du mois (±7 jours), au moins 3 fois."""
    pts = sorted((p for p in points if p.amount_cents >= min_amount), key=lambda p: (p.day, p.id))
    found = []
    for group in _clusters(pts, ratio=0.25, abs_tol=0):
        if len(group) < 3:
            continue
        code = _frequency_of([p.day for p in group], min_count=3, strict=True)
        if code == "mensuel" and _same_days([p.day for p in group], 7) and _stable([p.amount_cents for p in group], code, tol=0.25):
            found.append(_build(group, code, today))
    return found
