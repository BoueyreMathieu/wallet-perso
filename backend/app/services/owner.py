"""Ton identité de titulaire : les noms qui désignent TES virements.

Une opération dont le vendeur commence par une de ces signatures (« MONSIEUR DUPONT JEA »…) est un
virement entre tes comptes : catégorie « Transferts › Virement interne », hors statistiques.
(Le regroupement des variantes d'un même nom en un seul vendeur est fait par services/merchant_merge.)

Les signatures sont apprises du titulaire des exports CSV, et modifiables dans Paramètres › Préférences.
"""

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.categorize import is_own_name, normalize
from app.models import Merchant, Transaction
from app.seed import set_meta
from app.services.categorizing import get_owner_signatures, recategorize


def clean(names: list[str]) -> list[str]:
    out: list[str] = []
    for n in names:
        s = normalize(n)
        if len(s) >= 4 and s not in out:
            out.append(s)
    return out


def set_signatures(db: Session, names: list[str]) -> list[str]:
    sigs = clean(names)
    set_meta(db, "owner_signatures", json.dumps(sigs, ensure_ascii=False))
    db.flush()
    recategorize(db)  # les virements à ton nom passent (ou ne passent plus) en virement interne
    return sigs


def matching_merchants(db: Session, signatures: list[str] | None = None) -> list[Merchant]:
    sigs = get_owner_signatures(db) if signatures is None else signatures
    if not sigs:
        return []
    return [m for m in db.scalars(select(Merchant)) if is_own_name(normalize(m.name), sigs)]


def operations_count(db: Session, merchants: list[Merchant]) -> int:
    if not merchants:
        return 0
    ids = [m.id for m in merchants]
    return int(db.scalar(select(func.count(Transaction.id)).where(Transaction.merchant_id.in_(ids))) or 0)
