"""Moteur de catégorisation (pur Python, sans base de données).

Une règle associe un motif à une catégorie. Types de correspondance :
- « contient » : le motif apparaît comme mot(s) entier(s) dans le libellé (sans accents, en majuscules) ;
- « regex »    : expression régulière sur le libellé normalisé ;
- « marchand » : le nom du marchand est exactement le motif (règles créées par tes corrections).
Une règle peut être limitée à un vendeur (« service ») et à une fourchette de montant.

Les règles sont testées par priorité croissante ; la première qui correspond gagne.
Avant les règles, un virement contenant le nom du titulaire est reconnu comme virement interne.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def normalize(text: str | None) -> str:
    """« Prélèvement  Électricité » → « PRELEVEMENT ELECTRICITE »."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.upper()).strip()


@dataclass
class CompiledRule:
    id: int | None
    match_type: str
    pattern: str
    category_id: int | None
    priority: int
    # Service : règle limitée à un vendeur, avec éventuellement une fourchette de montant (valeur absolue).
    merchant: str | None = None
    amount_min: int | None = None
    amount_max: int | None = None
    _regex: re.Pattern | None = None

    def matches(self, label_norm: str, merchant_norm: str, amount: int | None = None) -> bool:
        if self.merchant is not None and merchant_norm != normalize(self.merchant):
            return False
        if self.amount_min is not None or self.amount_max is not None:
            if amount is None:
                return False
            a = abs(amount)
            if (self.amount_min is not None and a < self.amount_min) or (self.amount_max is not None and a > self.amount_max):
                return False
        if self.match_type == "marchand":
            return merchant_norm == normalize(self.pattern)
        if not self.pattern.strip():
            return self.merchant is not None  # service défini seulement par le montant
        if self._regex is None:
            if self.match_type == "regex":
                self._regex = re.compile(self.pattern, re.IGNORECASE)
            else:
                self._regex = re.compile(r"(?<![A-Z0-9])" + re.escape(normalize(self.pattern)) + r"(?![A-Z0-9])")
        return bool(self._regex.search(label_norm))


def owner_signatures(holder: str | None) -> list[str]:
    """« MONSIEUR DUPONT JEAN » → ["MONSIEUR DUPONT"] (civilité + nom, souvent tronqué ensuite)."""
    words = normalize(holder).split()
    return [" ".join(words[:2])] if len(words) >= 2 else []


def is_own_transfer(label_norm: str, signatures: list[str]) -> bool:
    return label_norm.startswith("VIREMENT") and any(s and s in label_norm for s in signatures)


def find_category(
    rules: list[CompiledRule],
    raw_label: str,
    merchant: str | None,
    signatures: list[str],
    internal_transfer_category_id: int | None,
    amount: int | None = None,
) -> tuple[int | None, CompiledRule | None]:
    merchant_norm = normalize(merchant)
    # On cherche aussi dans le nom du marchand résolu (ex. « MONOP PARIS » → « Monoprix »).
    label_norm = normalize(raw_label) + (" | " + merchant_norm if merchant_norm else "")
    # Les règles issues de tes corrections (priorité < 50) passent avant tout le reste.
    for r in rules:
        if r.priority >= 50:
            break
        if r.matches(label_norm, merchant_norm, amount):
            return r.category_id, r
    if internal_transfer_category_id and is_own_transfer(label_norm, signatures):
        return internal_transfer_category_id, None
    for r in rules:
        if r.priority >= 50 and r.matches(label_norm, merchant_norm, amount):
            return r.category_id, r
    return None, None
