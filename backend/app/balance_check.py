"""Contrôle de cohérence d'un compte synchronisé (pur Python, sans base).

La banque donne un solde à chaque synchro. Entre deux soldes, la différence doit être égale à la somme des opérations
reçues entre les deux dates. Sinon, il manque une opération, ou une est en double.

Les dates de la banque (date d'opération / de valeur, solde arrêté la veille…) peuvent décaler les choses d'un jour :
on essaie la fenêtre telle quelle, puis décalée d'un jour dans chaque sens, et on garde l'écart le plus petit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Gap:
    gap_cents: int  # solde de la banque − solde attendu d'après les opérations (> 0 : il manque une rentrée…)
    since: date  # premier solde de la période contrôlée
    until: date  # dernier solde


def balance_gap(snapshots: list[tuple[date, int]], ops: list[tuple[date, int]], since: date) -> Gap | None:
    """Écart sur la période [premier solde ≥ since, dernier solde], ou None s'il n'y a pas deux soldes à comparer.
    Un écart nul (Gap.gap_cents == 0) veut dire que tout est cohérent."""
    snaps = sorted((d, v) for d, v in snapshots if d >= since)
    if len(snaps) < 2:
        return None
    (d1, s1), (d2, s2) = snaps[0], snaps[-1]
    best: int | None = None
    for shift in (0, -1, 1):
        lo, hi = d1 + timedelta(days=shift), d2 + timedelta(days=shift)
        moved = sum(a for d, a in ops if lo < d <= hi)
        gap = (s2 - s1) - moved
        if best is None or abs(gap) < abs(best):
            best = gap
    return Gap(best or 0, d1, d2)
