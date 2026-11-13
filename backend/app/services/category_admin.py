"""Gestion des catégories par l'utilisateur : créer, modifier, déplacer, supprimer.

Suppression : les opérations de la catégorie (et de ses sous-catégories) sont soit déplacées vers
une autre catégorie, soit remises « à catégoriser » (puis les règles restantes sont réappliquées :
celles qui ne trouvent rien apparaissent dans « À catégoriser »). Les règles et vendeurs qui
pointaient vers la catégorie suivent le même chemin.

Une catégorie par défaut supprimée ou renommée est mémorisée pour ne jamais être recréée au
démarrage (app_meta : hidden_default_categories, category_aliases).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.models import Budget, Category, Merchant, Rule, Transaction
from app.seed import PROTECTED_PATHS, category_aliases, category_paths, hidden_defaults, set_meta
from app.services.categorizing import Categorizer


class CategoryError(ValueError):
    pass


def path_of(db: Session, cat: Category) -> str:
    parent = db.get(Category, cat.parent_id) if cat.parent_id else None
    return f"{parent.name}/{cat.name}" if parent else cat.name


def is_protected(db: Session, cat: Category) -> bool:
    return path_of(db, cat) in PROTECTED_PATHS


def protected_ids(db: Session) -> set[int]:
    paths = category_paths(db)
    return {paths[p] for p in PROTECTED_PATHS if p in paths}


def children(db: Session, cat: Category) -> list[Category]:
    return list(db.scalars(select(Category).where(Category.parent_id == cat.id)))


def _check_unique(db: Session, name: str, parent_id: int | None, exclude: int | None = None) -> None:
    q = select(Category).where(func.lower(Category.name) == name.strip().lower())
    q = q.where(Category.parent_id.is_(None)) if parent_id is None else q.where(Category.parent_id == parent_id)
    other = db.scalar(q)
    if other is not None and other.id != exclude:
        raise CategoryError(f"La catégorie « {name.strip()} » existe déjà à cet endroit.")


def _parent(db: Session, parent_id: int | None) -> Category | None:
    if parent_id is None:
        return None
    parent = db.get(Category, parent_id)
    if parent is None:
        raise CategoryError("Catégorie parente introuvable.")
    if parent.parent_id is not None:
        raise CategoryError("Deux niveaux maximum : une sous-catégorie ne peut pas avoir de sous-catégories.")
    return parent


def create(db: Session, name: str, parent_id: int | None, kind: str | None, color: str | None, icon: str | None) -> Category:
    parent = _parent(db, parent_id)
    _check_unique(db, name, parent_id)
    cat = Category(
        name=name.strip(),
        parent_id=parent_id,
        kind=parent.kind if parent else (kind or "depense"),
        color=color or (parent.color if parent else "#64748b"),
        icon=icon or None,
    )
    db.add(cat)
    db.flush()
    return cat


def _remember_paths(db: Session, cat: Category) -> None:
    """Avant un renommage / déplacement : les anciens chemins restent associés à la catégorie."""
    aliases = category_aliases(db)
    old = path_of(db, cat)
    aliases[old] = cat.id
    for ch in children(db, cat):
        aliases[f"{old}/{ch.name}"] = ch.id
    set_meta(db, "category_aliases", json.dumps(aliases, ensure_ascii=False))


def _refresh_transfer_flags(db: Session, ids: list[int], kind: str) -> None:
    db.execute(update(Transaction).where(Transaction.category_id.in_(ids)).values(is_transfer=kind == "transfert"))


def update_category(
    db: Session,
    cat: Category,
    *,
    name: str | None = None,
    color: str | None = None,
    icon: str | None = None,
    kind: str | None = None,
    move: bool = False,
    parent_id: int | None = None,
) -> Category:
    protected = is_protected(db, cat)
    renamed = name is not None and name.strip() != cat.name
    moved = move and parent_id != cat.parent_id
    if protected and (renamed or moved or (kind and kind != cat.kind)):
        raise CategoryError("Cette catégorie sert à reconnaître les virements internes : on peut changer sa couleur ou son icône, pas plus.")
    if moved:
        if parent_id == cat.id:
            raise CategoryError("Une catégorie ne peut pas être sa propre parente.")
        if parent_id is not None and children(db, cat):
            raise CategoryError("Cette catégorie a des sous-catégories : elle ne peut pas devenir une sous-catégorie.")
        _parent(db, parent_id)
    target_parent = parent_id if moved else cat.parent_id
    if renamed or moved:
        _check_unique(db, name or cat.name, target_parent, exclude=cat.id)
        _remember_paths(db, cat)
    if renamed:
        cat.name = name.strip()  # type: ignore[union-attr]
    if moved:
        cat.parent_id = parent_id
        parent = db.get(Category, parent_id) if parent_id else None
        if parent is not None and cat.kind != parent.kind:
            cat.kind = parent.kind
            _refresh_transfer_flags(db, [cat.id], cat.kind)
    if color is not None:
        if cat.parent_id is None and color != cat.color:
            # Les sous-catégories qui avaient la couleur de la catégorie principale la suivent (nuancées à l'affichage).
            for ch in children(db, cat):
                if (ch.color or "").lower() == (cat.color or "").lower():
                    ch.color = color
        cat.color = color
    if icon is not None:
        cat.icon = icon or None
    if kind is not None and kind != cat.kind:
        if cat.parent_id is not None:
            raise CategoryError("Le type (dépense, revenu, transfert) se règle sur la catégorie principale.")
        ids = [cat.id] + [c.id for c in children(db, cat)]
        for c in db.scalars(select(Category).where(Category.id.in_(ids))):
            c.kind = kind
        _refresh_transfer_flags(db, ids, kind)
    db.flush()
    return cat


def usage(db: Session) -> dict[int, dict[str, int]]:
    out: dict[int, dict[str, int]] = {}

    def add(rows, key):
        for cid, n in rows:
            if cid is not None:
                out.setdefault(cid, {"transactions": 0, "rules": 0, "merchants": 0})[key] = int(n)

    add(db.execute(select(Transaction.category_id, func.count()).group_by(Transaction.category_id)).all(), "transactions")
    add(db.execute(select(Rule.category_id, func.count()).group_by(Rule.category_id)).all(), "rules")
    add(db.execute(select(Merchant.default_category_id, func.count()).group_by(Merchant.default_category_id)).all(), "merchants")
    return out


@dataclass
class DeleteResult:
    deleted: int
    transactions: int
    moved_to: int | None
    rules: int
    merchants: int
    to_categorize: int


def delete_category(db: Session, cat: Category, move_to: int | None = None) -> DeleteResult:
    if is_protected(db, cat):
        raise CategoryError("Cette catégorie sert à reconnaître les virements internes : elle ne peut pas être supprimée.")
    subs = children(db, cat)
    ids = [cat.id] + [c.id for c in subs]
    if any(i in protected_ids(db) for i in ids):
        raise CategoryError("Cette catégorie contient une sous-catégorie indispensable (virements internes).")
    target = None
    if move_to is not None:
        target = db.get(Category, move_to)
        if target is None or target.id in ids:
            raise CategoryError("Catégorie de destination invalide.")

    # Chemins des catégories par défaut supprimées : à ne jamais recréer.
    hidden = hidden_defaults(db)
    parent_path = path_of(db, cat)
    hidden.add(parent_path)
    hidden.update(f"{parent_path}/{c.name}" for c in subs)
    aliases = category_aliases(db)
    hidden.update(old for old, cid in aliases.items() if cid in ids)
    set_meta(db, "hidden_default_categories", json.dumps(sorted(hidden), ensure_ascii=False))
    set_meta(db, "category_aliases", json.dumps({k: v for k, v in aliases.items() if v not in ids}, ensure_ascii=False))

    txs = list(
        db.scalars(select(Transaction).options(selectinload(Transaction.merchant)).where(Transaction.category_id.in_(ids)))
    )
    rules = list(db.scalars(select(Rule).where(Rule.category_id.in_(ids))))
    merchants = list(db.scalars(select(Merchant).where(Merchant.default_category_id.in_(ids))))

    if target is not None:
        for t in txs:
            t.category_id, t.is_transfer = target.id, target.kind == "transfert"
        for r in rules:
            r.category_id = target.id
        for m in merchants:
            m.default_category_id = target.id
    else:
        rule_ids = [r.id for r in rules]
        if rule_ids:
            db.execute(update(Transaction).where(Transaction.rule_id.in_(rule_ids)).values(rule_id=None))
        for r in rules:
            db.delete(r)
        for m in merchants:
            m.default_category_id = None
        for t in txs:
            t.category_id, t.category_locked, t.is_transfer, t.rule_id = None, False, False, None

    for b in db.scalars(select(Budget).where(Budget.category_id.in_(ids))):
        db.delete(b)
    db.flush()
    for c in subs:
        db.delete(c)
    db.delete(cat)
    db.flush()

    left = 0
    if target is None and txs:
        # Les autres règles (vendeur, défaut) peuvent retrouver une catégorie ; sinon « À catégoriser ».
        Categorizer(db).apply(txs)
        left = sum(1 for t in txs if t.category_id is None)
    db.flush()
    return DeleteResult(len(ids), len(txs), target.id if target else None, len(rules), len(merchants), left)


