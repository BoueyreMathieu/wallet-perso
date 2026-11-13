"""Virements entre mes comptes : appariement des deux lignes d'un même virement.

Un virement du compte courant vers le livret apparaît deux fois : −X sur le courant, +X sur le livret.
Sans appariement, il gonfle à la fois les dépenses et les revenus. Une fois apparié :
- les deux lignes sont des transferts (hors statistiques), catégorie « Virement interne »
  (ou une autre catégorie de type transfert déjà choisie, ex. « Épargne / investissement ») ;
- chaque ligne pointe vers l'autre (transfer_pair_id) et details["virement_interne"] = True.

Détection automatique prudente : comptes différents (hors PayPal, géré par le rapprochement PayPal),
montants opposés, dates à ±3 jours, et les deux libellés ressemblent à un virement (ou la ligne est
déjà rangée dans une catégorie de transfert). En cas de doute (plusieurs candidats aussi proches),
rien n'est apparié. « Dissocier » défait l'appariement et l'empêche de revenir automatiquement.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Account, Category, Transaction
from app.seed import INTERNAL_TRANSFER_PATH, category_paths
from app.services.categorizing import Categorizer

MAX_DAYS = 3
TRANSFER_WORDS = re.compile(r"\bVIR\b|VIREMENT|\bVIRT?\b|TRANSFERT|VERSEMENT|\bVRT\b|EPARGNE|ÉPARGNE|LIVRET", re.IGNORECASE)
MARK = "virement_interne"


class TransferError(ValueError):
    pass


def _looks_like_transfer(t: Transaction, kinds: dict[int, str]) -> bool:
    if t.category_id is not None and kinds.get(t.category_id) == "transfert":
        return True
    if t.category_locked:
        return False  # rangée à la main dans une catégorie de dépense/revenu : on n'y touche pas
    return bool(TRANSFER_WORDS.search(t.raw_label or ""))


def _candidates(db: Session) -> list[Transaction]:
    q = (
        select(Transaction)
        .options(selectinload(Transaction.account))
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.type != "paypal",
            Transaction.transfer_pair_id.is_(None),
            Transaction.linked_id.is_(None),
            Transaction.counted.is_(True),
        )
    )
    return [t for t in db.scalars(q) if not (t.details or {}).get("no_pair") and not (t.details or {}).get("via")]


def pair(db: Session, a: Transaction, b: Transaction, internal_id: int | None, kinds: dict[int, str]) -> None:
    a.transfer_pair_id, b.transfer_pair_id = b.id, a.id
    # Même catégorie des deux côtés : une catégorie de transfert déjà choisie (ex. « Épargne »), sinon « Virement interne ».
    chosen = next((t.category_id for t in (a, b) if t.category_id is not None and kinds.get(t.category_id) == "transfert"), internal_id)
    for t in (a, b):
        details = {k: v for k, v in (t.details or {}).items() if k != "no_pair"}
        details[MARK] = True
        t.details = details
        t.is_transfer = True
        if t.category_id != chosen:
            t.category_id, t.rule_id = chosen, None


def detect(db: Session) -> int:
    """Apparie automatiquement les virements internes évidents. Renvoie le nombre de paires créées."""
    kinds = dict(db.execute(select(Category.id, Category.kind)).all())
    internal_id = category_paths(db).get(INTERNAL_TRANSFER_PATH)
    txs = [t for t in _candidates(db) if _looks_like_transfer(t, kinds)]
    credits: dict[int, list[Transaction]] = defaultdict(list)
    for t in txs:
        if t.amount_cents > 0:
            credits[t.amount_cents].append(t)

    options: dict[int, list[tuple[int, Transaction]]] = {}
    debits = {t.id: t for t in txs if t.amount_cents < 0}
    for d in debits.values():
        lo, hi = d.booked_at - timedelta(days=MAX_DAYS), d.booked_at + timedelta(days=MAX_DAYS)
        cands = [
            (abs((c.booked_at - d.booked_at).days), c)
            for c in credits.get(-d.amount_cents, [])
            if c.account_id != d.account_id and lo <= c.booked_at <= hi
        ]
        if cands:
            options[d.id] = sorted(cands, key=lambda x: (x[0], x[1].id))

    # Ambiguïté côté crédit : un même crédit candidat à égalité pour deux débits → on s'abstient.
    best_for_credit: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for did, cands in options.items():
        for dist, c in cands:
            best_for_credit[c.id].append((dist, did))

    used: set[int] = set()
    created = 0
    for did in sorted(options, key=lambda i: (options[i][0][0], i)):
        free = [(dist, c) for dist, c in options[did] if c.id not in used]
        if not free or (len(free) > 1 and free[0][0] == free[1][0]):
            continue
        dist, credit = free[0]
        rivals = [x for x in best_for_credit[credit.id] if x[1] != did and x[1] in options and x[0] == dist]
        if rivals:
            continue
        pair(db, debits[did], credit, internal_id, kinds)
        used.add(credit.id)
        created += 1
    db.flush()
    return created


def pair_manually(db: Session, a: Transaction, b: Transaction) -> None:
    if a.id == b.id or a.account_id == b.account_id:
        raise TransferError("Choisis deux opérations sur deux comptes différents.")
    if a.amount_cents != -b.amount_cents:
        raise TransferError("Les deux montants doivent être opposés (−X d'un côté, +X de l'autre).")
    for t in (a, b):
        if t.linked_id is not None or (t.transfer_pair_id is not None and t.transfer_pair_id not in (a.id, b.id)):
            raise TransferError("Une des opérations est déjà rapprochée d'une autre : dissocie-la d'abord.")
    kinds = dict(db.execute(select(Category.id, Category.kind)).all())
    pair(db, a, b, category_paths(db).get(INTERNAL_TRANSFER_PATH), kinds)
    for t in (a, b):
        t.category_locked = False
    db.flush()


def unpair(db: Session, t: Transaction) -> None:
    if not (t.details or {}).get(MARK):
        raise TransferError("Cette opération n'est pas un virement entre tes comptes.")
    other = db.get(Transaction, t.transfer_pair_id) if t.transfer_pair_id else None
    rows = [x for x in (t, other) if x is not None]
    for x in rows:
        details = dict(x.details or {})
        details.pop(MARK, None)
        details["no_pair"] = True
        x.details = details
        x.transfer_pair_id = None
        x.category_locked = False
    db.flush()
    for x in rows:
        db.refresh(x, ["merchant"])
    Categorizer(db).apply(rows)
    db.flush()


def pair_account_name(db: Session, t: Transaction) -> str | None:
    if not (t.details or {}).get(MARK) or not t.transfer_pair_id:
        return None
    other = db.get(Transaction, t.transfer_pair_id)
    return other.account.name if other is not None else None
