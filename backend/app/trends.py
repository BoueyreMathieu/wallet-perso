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
4. **Changement de rythme** : si les 2 derniers mois s'écartent nettement d'avant (dans le même sens), le niveau
   suit surtout le récent (nouveau logement, nouvelles habitudes…).
5. **Habitudes par vendeur** : un vendeur fréquent (supermarché, boulangerie, bar du vendredi…) est placé à ses jours
   habituels, avec son montant habituel ; le reste de la catégorie suit le rythme général.
6. **Mois en cours** : ce qui reste à dépenser = habitude du mois − déjà dépensé (en gardant un minimum : on finit
   rarement le mois sans rien acheter) ; en retard sur son rythme, on rattrape la moitié de l'écart.
7. **Fourchette** : mois « bons » et « mauvais » de chaque catégorie (1er et 3e quartiles) → prévision prudente / optimiste.
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


SHIFT_RATIO = 1.3


def trend_level(values: list[int]) -> int:
    """Niveau mensuel : moyenne pondérée, sauf changement de rythme net sur les 2 derniers mois (tous deux > +30 % ou
    < −30 % par rapport à la médiane d'avant) : le niveau suit alors surtout ces 2 mois (70 %)."""
    base = weighted_level(values)
    vals = winsorize(values[-MAX_MONTHS:])
    if len(vals) < 5:
        return base
    before = median(vals[:-2])
    last2 = vals[-2:]
    if before > 0 and (all(v > before * SHIFT_RATIO for v in last2) or all(v < before / SHIFT_RATIO for v in last2)):
        return round(0.7 * sum(last2) / 2 + 0.3 * base)
    return base


def band(values: list[int], level: int) -> tuple[float, float]:
    """Mois « bons » / « mauvais » relatifs au niveau : (1er quartile / niveau, 3e quartile / niveau), bornés."""
    vals = sorted(winsorize(values[-MAX_MONTHS:]))
    if len(vals) < 4 or level <= 0:
        return 0.85, 1.15
    q1, q3 = vals[len(vals) // 4], vals[(3 * len(vals)) // 4]
    return min(max(q1 / level, 0.5), 1.0), max(min(q3 / level, 1.8), 1.0)


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


# --- Habitudes par vendeur -----------------------------------------------------------------------

HABIT_WINDOW_DAYS = 91
HABIT_MIN_VISITS = 6  # au moins toutes les 2 semaines sur 3 mois


@dataclass
class Habit:
    """Vendeur fréquent : passages par semaine, répartition par jour de la semaine (somme 1), montant habituel."""

    key: int
    label: str
    amount: int
    per_week: float
    weekday: list[float]

    @property
    def monthly(self) -> float:
        return self.per_week * self.amount * 52.18 / 12

    def on(self, d: date) -> float:
        return self.per_week * self.weekday[d.weekday()] * self.amount


def learn_habit(key: int, label: str, visits: list[tuple[date, int]], today: date) -> Habit | None:
    """Habitude d'un vendeur d'après ses passages des 3 derniers mois (montants positifs) ; None s'il n'est pas assez
    fréquent ou plus fréquenté (dernier passage il y a plus de 3 semaines)."""
    recent = [(d, a) for d, a in visits if 0 <= (today - d).days <= HABIT_WINDOW_DAYS and a > 0]
    if len(recent) < HABIT_MIN_VISITS or (today - max(d for d, _ in recent)).days > 21:
        return None
    counts = [0] * 7
    for d, _ in recent:
        counts[d.weekday()] += 1
    n = len(recent)
    weekday = [(c + 0.25) / (n + 1.75) for c in counts]  # léger lissage : un jour jamais vu n'est pas impossible
    return Habit(key, label, round(median(a for _, a in recent)), n / (HABIT_WINDOW_DAYS / 7), weekday)


def unit_expected(monthly: float, habits: list[Habit], profile: Profile, start: date, end: date) -> dict[date, float]:
    """Dépense attendue chaque jour pour une catégorie : ses vendeurs habituels à leurs jours (ramenés au niveau de la
    catégorie s'ils le dépassent), le reste réparti selon le rythme de la couche."""
    if monthly <= 0 or end < start:
        return {}
    hmonth = sum(h.monthly for h in habits)
    scale = min(1.0, monthly / hmonth) if hmonth > 0 else 0.0
    out = expected_between(max(monthly - hmonth * scale, 0.0), start, end, profile)
    if scale > 0:
        d = start
        while d <= end:
            out[d] = out.get(d, 0.0) + scale * sum(h.on(d) for h in habits)
            d = date.fromordinal(d.toordinal() + 1)
    return out


MIN_REST_SHARE = 0.3  # même « en avance », il reste au moins 30 % de la dépense habituelle de fin de mois
CATCH_UP = 0.5  # « en retard » sur son rythme : on rattrape la moitié de l'écart


def rest_of_month(rest_by_rhythm: float, monthly: float, spent: float, expected_so_far: float) -> float:
    """Reste à dépenser ce mois-ci pour une catégorie.

    - au-dessus de son rythme (déjà beaucoup dépensé) : habitude du mois − déjà dépensé, au moins 30 % du reste habituel ;
    - en dessous : le reste habituel + la moitié de ce qui n'a pas encore été dépensé en plus."""
    if spent >= expected_so_far:
        return max(monthly - spent, MIN_REST_SHARE * rest_by_rhythm)
    gap = max(monthly - spent, 0.0)
    return rest_by_rhythm + CATCH_UP * max(gap - rest_by_rhythm, 0.0)


# --- Dépenses occasionnelles (coiffeur, formation…) -------------------------------------------------

REGULAR_SHARE = 0.6  # dépense au moins 6 mois sur 10 : régulière (répartie chaque mois)
SAME_OCCASION_DAYS = 7  # achats à moins d'une semaine d'écart : une seule « occasion »


@dataclass
class Occasional:
    """Dépense qui revient de temps en temps : montant d'une fois, intervalle habituel, prochaine fois attendue."""

    amount: int
    every_days: int
    next_date: date
    count: int

    @property
    def monthly(self) -> float:
        return self.amount * 30.44 / self.every_days

    @property
    def yearly(self) -> float:
        return self.amount * 365.25 / self.every_days


def occasions(visits: list[tuple[date, int]]) -> list[tuple[date, int]]:
    """Regroupe les achats proches (moins d'une semaine d'écart) en occasions : (date, montant total)."""
    out: list[list] = []
    for d, a in sorted(visits):
        if out and (d - out[-1][2]).days <= SAME_OCCASION_DAYS:
            out[-1][1] += a
            out[-1][2] = d
        else:
            out.append([d, a, d])
    return [(d, a) for d, a, _ in out]


def classify(history: list[int], visits: list[tuple[date, int]], today: date) -> str | Occasional | None:
    """Comment prévoir une catégorie sans date fixe :

    - « regular » : dépense presque tous les mois (au moins 60 % des mois depuis la première fois) → répartie chaque mois ;
    - Occasional : de temps en temps (coiffeur tous les 3 mois…) → un montant d'un coup, à la prochaine date attendue ;
    - None : une seule fois (formation, gros achat), ou plus rien depuis longtemps → pas prévue."""
    active = sum(1 for v in history if v > 0)
    if len(history) >= 2 and active >= 2 and active / len(history) >= REGULAR_SHARE:
        return "regular"
    occ = occasions(visits)
    if len(occ) < 2:
        return None
    gaps = [(b[0] - a[0]).days for a, b in zip(occ, occ[1:])]
    every = max(int(median(gaps)), 14)
    last = occ[-1][0]
    if (today - last).days > max(2 * every, 60):
        return None  # plus rien depuis bien plus longtemps que d'habitude : arrêté
    nxt = date.fromordinal(last.toordinal() + every)
    if nxt <= today:
        nxt = date.fromordinal(today.toordinal() + 1)  # en retard : attendue bientôt
    return Occasional(round(median(a for _, a in occ)), every, nxt, len(occ))
