"""Format commun à toutes les sources de données.

Chaque source (fichier CSV, API bancaire, bibliothèque comme pytr…) produit un `Statement` :
le pipeline d'ingestion (app.services.ingest) s'occupe ensuite de tout le reste
(doublons, marchands, catégories, rapprochements). Ajouter un établissement = écrire
une fonction qui renvoie un Statement, sans toucher au reste.

Pur Python, sans base de données.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date


@dataclass
class RawTransaction:
    booked_at: date
    amount_cents: int
    raw_label: str
    # Clé stable de l'opération chez la source (sert au dédoublonnage).
    dedup_key: str
    merchant_hint: str | None = None
    external_id: str | None = None
    status: str | None = None  # « terminé », « en attente »…
    details: dict | None = None  # infos d'origine affichables (jamais d'adresse, téléphone, e-mail)
    # Opération purement technique (approvisionnement, réservation…) : visible mais hors statistiques.
    counted: bool = True
    force_category_path: str | None = None  # ex. « Transferts/PayPal »


@dataclass
class Statement:
    source: str  # « csv_credit_agricole », « csv_paypal », « enable_banking »…
    account_external_id: str | None
    account_label: str | None
    holder: str | None = None
    balance_date: date | None = None
    balance_cents: int | None = None
    transactions: list[RawTransaction] = field(default_factory=list)
    # Alias de marchands appris pendant la lecture (clé → nom), à mémoriser en base.
    merchant_aliases: dict[str, str] = field(default_factory=dict)

    @property
    def period(self) -> tuple[date, date] | None:
        if not self.transactions:
            return None
        days = [t.booked_at for t in self.transactions]
        return min(days), max(days)


def stable_hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
