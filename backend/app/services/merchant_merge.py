"""Fusion des vendeurs similaires (voir app/merchant_similarity.py).

- auto_merge : fusionne les groupes « sûrs » (même nom à une troncature / référence près), sauf si deux
  vendeurs du groupe ont des catégories choisies différentes (→ suggestion à la place) ;
- suggestions : groupes « probables » à confirmer dans la page Vendeurs ;
- ignore : « ce ne sont pas les mêmes » (mémorisé dans app_meta.merchant_merge_ignored).
Le vendeur gardé est celui qui a le plus d'opérations (à égalité : le nom le plus court).
"""

from __future__ import annotations

import json
from collections import defaultdict
from itertools import combinations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.merchant_similarity import bucket, relation
from app.models import Merchant, Transaction
from app.seed import get_meta, set_meta
from app.services.cleanup import merge_merchants

IGNORED_KEY = "merchant_merge_ignored"


class _UnionFind:
    def __init__(self):
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)

    def groups(self) -> list[list[int]]:
        out: dict[int, list[int]] = defaultdict(list)
        for x in self.parent:
            out[self.find(x)].append(x)
        return [sorted(g) for g in out.values() if len(g) > 1]


def _ignored(db: Session) -> set[tuple[int, int]]:
    return {tuple(sorted(p)) for p in json.loads(get_meta(db, IGNORED_KEY, "[]"))}  # type: ignore[misc]


def _counts(db: Session) -> dict[int, int]:
    return {mid: n for mid, n in db.execute(select(Transaction.merchant_id, func.count()).group_by(Transaction.merchant_id)).all() if mid}


def _pairs(merchants: list[Merchant]):
    buckets: dict[str, list[Merchant]] = defaultdict(list)
    for m in merchants:
        b = bucket(m.name)
        if b:
            buckets[b].append(m)
    for group in buckets.values():
        for a, b in combinations(group, 2):
            rel = relation(a.name, b.name)
            if rel:
                yield a, b, rel


def analyse(db: Session) -> tuple[list[list[Merchant]], list[list[Merchant]]]:
    """(groupes sûrs, groupes à confirmer)."""
    merchants = list(db.scalars(select(Merchant)))
    by_id = {m.id: m for m in merchants}
    ignored = _ignored(db)
    sure, maybe = _UnionFind(), _UnionFind()
    for a, b, rel in _pairs(merchants):
        pair = tuple(sorted((a.id, b.id)))
        conflict = a.default_category_id and b.default_category_id and a.default_category_id != b.default_category_id
        if rel == "sure" and not conflict:
            sure.union(a.id, b.id)
        elif pair not in ignored:
            maybe.union(a.id, b.id)
    sure_groups = [[by_id[i] for i in g] for g in sure.groups()]
    # Une suggestion qui ne relie que des vendeurs déjà fusionnés ensemble automatiquement n'a pas lieu d'être.
    merged_into = {m.id: g[0].id for g in sure_groups for m in g}
    maybe_groups = []
    for g in maybe.groups():
        if len({merged_into.get(i, i) for i in g}) > 1:
            maybe_groups.append([by_id[i] for i in g])
    return sure_groups, maybe_groups


def pick_target(group: list[Merchant], counts: dict[int, int]) -> Merchant:
    return sorted(group, key=lambda m: (-counts.get(m.id, 0), len(m.name), m.id))[0]


def merge_group(db: Session, group: list[Merchant], target: Merchant, name: str | None = None) -> int:
    from app.services.cleanup import rename_merchant

    moved = 0
    for m in group:
        if m.id != target.id:
            moved += merge_merchants(db, m, target)
    if name and name.strip() and name.strip() != target.name:
        rename_merchant(db, target, name)
    db.flush()
    return moved


def auto_merge(db: Session) -> int:
    """Fusionne les groupes sûrs. Renvoie le nombre de vendeurs absorbés."""
    sure_groups, _ = analyse(db)
    if not sure_groups:
        return 0
    counts = _counts(db)
    absorbed = 0
    for g in sure_groups:
        merge_group(db, g, pick_target(g, counts))
        absorbed += len(g) - 1
    return absorbed


def suggestions(db: Session) -> list[dict]:
    _, maybe_groups = analyse(db)
    counts = _counts(db)
    out = []
    for g in maybe_groups:
        target = pick_target(g, counts)
        out.append(
            {
                "merchants": [{"id": m.id, "name": m.name, "count": counts.get(m.id, 0)} for m in sorted(g, key=lambda m: -counts.get(m.id, 0))],
                "proposed_id": target.id,
            }
        )
    return sorted(out, key=lambda s: -sum(m["count"] for m in s["merchants"]))


def ignore(db: Session, ids: list[int]) -> None:
    pairs = _ignored(db) | {tuple(sorted(p)) for p in combinations(set(ids), 2)}
    set_meta(db, IGNORED_KEY, json.dumps(sorted(list(p) for p in pairs)))
    db.flush()


def find_existing(name: str, index: dict[str, list[Merchant]]) -> Merchant | None:
    """À l'import : un vendeur existant qui porte « sûrement » ce nom (troncature / référence près)."""
    for m in index.get(bucket(name), []):
        if relation(name, m.name) == "sure":
            return m
    return None
