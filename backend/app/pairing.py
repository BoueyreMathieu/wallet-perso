"""Rapprochement d'un prélèvement bancaire PayPal avec un achat PayPal payé en partie par le solde PayPal
(pur Python, sans base de données).

Quand PayPal utilise son propre solde en plus de la banque, le prélèvement bancaire (−B) est plus petit que
l'achat (−P) : l'égalité de montants ne marche plus. On associe alors le prélèvement à l'achat le plus proche
dans le temps dont le montant est supérieur, tant que le choix n'est pas ambigu (jamais de devinette)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Cand:
    id: int
    day: date
    amount_cents: int  # signé : un débit est négatif


def partial_pairs(banks: list[Cand], purchases: list[Cand], before: int = 7, after: int = 2) -> list[tuple[int, int]]:
    """Couples (id du prélèvement, id de l'achat). L'achat est plus gros que le prélèvement, daté de `before` jours
    avant à `after` jours après lui. Deux candidats à égale distance de dates : on ne rapproche pas."""
    options: dict[int, list[tuple[int, int]]] = {}
    for b in banks:
        if b.amount_cents >= 0:
            continue
        lo, hi = b.day - timedelta(days=before), b.day + timedelta(days=after)
        cands = [(abs((b.day - p.day).days), p.id) for p in purchases if p.amount_cents < b.amount_cents and lo <= p.day <= hi]
        if cands:
            options[b.id] = sorted(cands)
    taken: set[int] = set()
    pairs: list[tuple[int, int]] = []
    # Les cas les plus nets d'abord (écart de dates le plus faible).
    for bid in sorted(options, key=lambda i: (options[i][0][0], i)):
        free = [c for c in options[bid] if c[1] not in taken]
        if not free or (len(free) > 1 and free[0][0] == free[1][0]):
            continue
        taken.add(free[0][1])
        pairs.append((bid, free[0][1]))
    return pairs
