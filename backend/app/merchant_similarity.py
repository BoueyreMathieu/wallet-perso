"""Vendeurs « similaires » : même nom à une troncature ou une référence près (pur Python, sans base).

Les banques tronquent et décorent les noms de façon variable :
  « MONSIEUR DUPONT JEA », « MONSIEUR DUPONT JEAN », « MONSIEUR DUPONT JEAN 12 »
  « CARREFOUR MARKET 1234 », « CARREFOUR MARKET 5678 »
Relation entre deux noms :
- « sure »  : même nom une fois retirées les références finales (nombres, codes), ou l'un est le début de
              l'autre (troncature) avec au moins 2 mots et 10 caractères → fusion automatique ;
- « maybe » : mêmes deux premiers mots mais suite différente (« … JEAN » / « … PAUL ») → on demande ;
- None      : rien à voir.
"""

from __future__ import annotations

import os
import re

from app.categorize import normalize
from app.label_cleaning import clean_payee, is_generic

MIN_PREFIX = 10


def core(name: str | None) -> str:
    """Nom normalisé sans les références finales : « Carrefour Market 1234 » → « CARREFOUR MARKET ».
    Un libellé bancaire générique (« Paiement par carte X1234 … ») est d'abord réduit au vendeur qu'il contient."""
    if is_generic(name):
        name = clean_payee(name)
    words = re.findall(r"[A-Z0-9]+", normalize(name))
    while len(words) > 1 and any(c.isdigit() for c in words[-1]):
        words.pop()
    return " ".join(words)


def relation(a: str | None, b: str | None) -> str | None:
    ka, kb = core(a), core(b)
    if not ka or not kb or len(min(ka, kb, key=len)) < 3:
        return None
    if ka == kb:
        return "sure"
    short, long = sorted((ka, kb), key=len)
    sw, lw = short.split(), long.split()
    if len(sw) >= 2 and len(short) >= MIN_PREFIX and long.startswith(short):
        return "sure"
    if len(sw) >= 2 and len(lw) >= 2 and sw[:2] == lw[:2] and len(os.path.commonprefix([short, long])) >= MIN_PREFIX:
        return "maybe"
    return None


def bucket(name: str | None) -> str:
    """Seuls les noms qui commencent par le même mot sont comparés."""
    c = core(name)
    return c.split(" ", 1)[0] if c else ""
