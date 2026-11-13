"""Tendances de dépenses (cœur sans base de données, testable seul).

Pour les dépenses sans date fixe (essentiels, plaisirs, factures irrégulières) et les revenus non récurrents :

1. **Niveau mensuel** : moyenne pondérée de TOUS les mois disponibles (12 au plus), les plus récents comptant plus
   (demi-vie de 3 mois : un mois d'il y a 3 mois pèse moitié moins que le dernier). Un mois exceptionnel (plus de
   3 fois la médiane, ex. un ordinateur) est écrêté pour ne pas fausser la tendance. Plus il y a de mois, plus
   l'estimation est stable : elle s'affine mois après mois.
2. **Sens** : les 3 derniers mois comparés aux 3 précédents (hausse / baisse / stable).
3. **Rythme dans le mois** : quels jours on dépense (le samedi pour les courses, le vendredi soir pour les sorties,
   en début de mois après la paie…). Facteurs par jour de la semaine et par tiers de mois, appris sur tout
   l'historique et ramenés vers « uniforme » tant qu'il y a peu de données.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from statistics import median

HALF_LIFE_MONTHS = 3.0
MAX_MONTHS = 12
OUTLIER_FACTOR = 3.0


def winsorize(values: list[int]) -> list[int]:
    """Écrête les mois aberrants (> 3 × la médiane des mois non nuls)."""
    nonzero = [v for v in values if v > 0]
    if len(nonzero) < 3:
        return list(values)
    cap = OUTLIER_FACTOR * median(nonzero)
    return [min(v, round(cap)) for v in values]


def weighted_level(values: list[int], half_life: float = HALF_LIFE_MONTHS) -> int:
    """Moyenne pondérée (du plus ancien au plus récent), poids divisé par 2 tous les `half_life` mois."""
    vals = winsorize(values[-MAX_MONTHS:])
    if not vals:
        return 0
    n = len(vals)
    weights = [0.5 ** ((n - 1 - i) / half_life) for i in range(n)]
    return round(sum(w * v for w, v in zip(weights, vals)) / sum(weights))


def direction(values: list[int]) -> str:
    """« hausse », « baisse » ou « stable » : 3 derniers mois vs 3 précédents (±10 %)."""
    if len(values) < 4:
        return "stable"
    recent = sum(values[-3:]) / 3
    before_vals = values[-6:-3]
    before = sum(before_vals) / len(before_vals)
    if before <= 0:
        return "hausse" if recent > 0 else "stable"
    ratio = recent / before
    return "hausse" if ratio > 1.10 else "baisse" if ratio < 0.90 else "stable"


@dataclass
class Profile:
    """Facteurs multiplicatifs (moyenne 1) : jour de la semaine (lundi = 0) et tiers du mois (1-10, 11-20, 21+)."""

    weekday: list[float] = field(default_factory=lambda: [1.0] * 7)
    third: list[float] = field(default_factory=lambda: [1.0] * 3)


def _third(d: date) -> int:
    return 0 if d.day <= 10 else 1 if d.day <= 20 else 2


def learn_profile(amounts: list[tuple[date, int]], months: int) -> Profile:
    """Profil appris sur l'historique ; ramené vers l'uniforme quand il y a peu de mois (confiance m / (m + 3))."""
    total = sum(a for _, a in amounts)
    if total <= 0 or months <= 0:
        return Profile()
    trust = months / (months + 3)
    wd = [0.0] * 7
    th = [0.0] * 3
    for d, a in amounts:
        wd[d.weekday()] += a
        th[_third(d)] += a
    # Part observée / part attendue si c'était uniforme (1/7 par jour de semaine ; ~10/30.4 par tiers).
    expected_th = [10 / 30.44, 10 / 30.44, 10.44 / 30.44]
    weekday = [1 + trust * ((w / total) * 7 - 1) for w in wd]
    third = [1 + trust * ((t / total) / e - 1) for t, e in zip(th, expected_th)]
    return Profile(weekday=[max(x, 0.05) for x in weekday], third=[max(x, 0.05) for x in third])


def month_weights(year: int, month: int, profile: Profile) -> dict[date, float]:
    """Part de la dépense du mois attendue chaque jour (somme = 1)."""
    days = calendar.monthrange(year, month)[1]
    raw = {}
    for day in range(1, days + 1):
        d = date(year, month, day)
        raw[d] = profile.weekday[d.weekday()] * profile.third[_third(d)]
    total = sum(raw.values())
    return {d: w / total for d, w in raw.items()}


def expected_between(monthly: float, start: date, end: date, profile: Profile) -> dict[date, float]:
    """Dépense attendue chaque jour de start à end inclus (montant mensuel réparti selon le profil)."""
    out: dict[date, float] = {}
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        for d, w in month_weights(y, m, profile).items():
            if start <= d <= end:
                out[d] = monthly * w
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def apply_caps(units: dict[int | None, float], parents: dict[int, int | None], caps: dict[int, float]) -> dict[int | None, float]:
    """Plafonne les montants mensuels attendus par catégorie (budgets ou objectifs).

    - plafond sur une sous-catégorie : s'applique à elle seule ;
    - plafond sur une catégorie principale : s'applique à elle et ses sous-catégories, réduites proportionnellement.
    Un plafond plus haut que la tendance ne change rien (on ne dépense pas plus parce que le budget le permet)."""
    out = dict(units)
    for cid, cap in caps.items():
        if parents.get(cid) is not None and cid in out:
            out[cid] = min(out[cid], cap)
    for cid, cap in caps.items():
        if parents.get(cid) is None:
            family = [c for c in out if c == cid or (c is not None and parents.get(c) == cid)]
            total = sum(out[c] for c in family)
            if total > cap > 0 or (cap == 0 and total > 0):
                ratio = cap / total if total else 0
                for c in family:
                    out[c] = out[c] * ratio
    return out
