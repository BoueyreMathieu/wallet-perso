"""Couches de dépenses pour les prévisions (cœur sans base de données, testable seul).

- fixe      : charges « incompressibles » — tous les récurrents (loyer, abonnements, assurances, crédits…) et les
              catégories de charges même quand elles ne tombent pas à date fixe (énergie, impôts…) ;
- essentiel : dépenses courantes nécessaires, sans date fixe (courses, carburant, santé…) ;
- plaisir   : dépenses courantes non essentielles (sorties, bars, restaurants, livraisons, shopping…).

Une opération reliée à un récurrent est toujours « fixe ». Sinon, la nature vient de sa catégorie : réglage de
l'utilisateur, sinon valeur par défaut ci-dessous, sinon celle de la catégorie principale, sinon « essentiel ».
"""

from __future__ import annotations

from statistics import median

NATURES = ("fixe", "essentiel", "plaisir")
NATURE_LABELS = {"fixe": "Charges fixes", "essentiel": "Dépenses essentielles", "plaisir": "Plaisirs et envies"}

DEFAULT_NATURES: dict[str, str] = {
    # Catégories principales
    "Alimentation": "essentiel",
    "Logement": "fixe",
    "Transport": "essentiel",
    "Abonnements": "fixe",
    "Loisirs": "plaisir",
    "Shopping": "plaisir",
    "Santé": "essentiel",
    "Beauté & soins": "plaisir",
    "Banque & impôts": "fixe",
    "Assurances": "fixe",
    "Éducation & formation": "essentiel",
    "Animaux": "essentiel",
    "Dons & associations": "plaisir",
    "Famille & amis": "essentiel",
    "Travail": "essentiel",
    "Divers": "essentiel",
    # Exceptions dans une famille
    "Alimentation/Restaurants": "plaisir",
    "Alimentation/Fast-food": "plaisir",
    "Alimentation/Livraison": "plaisir",
    "Alimentation/Cave / alcool": "plaisir",
    "Logement/Travaux / maison": "essentiel",
    "Logement/Ameublement / déco": "plaisir",
    "Logement/Électroménager": "essentiel",
    "Transport/Taxi / VTC": "plaisir",
    "Transport/Train / avion": "plaisir",
    "Transport/Location véhicule": "plaisir",
    "Transport/Assurance auto": "fixe",
    "Santé/Mutuelle": "fixe",
    "Beauté & soins/Coiffeur": "essentiel",
    "Banque & impôts/Retraits d'espèces": "essentiel",
    "Banque & impôts/Amendes": "essentiel",
    "Éducation & formation/Frais de scolarité": "fixe",
    "Dons & associations/Cotisations associatives": "fixe",
    "Famille & amis/Aide familiale": "fixe",
}


def effective_natures(
    own: dict[int, str | None], parents: dict[int, int | None], paths: dict[str, int]
) -> dict[int, str]:
    """Nature effective de chaque catégorie (réglage → défaut → catégorie principale → essentiel)."""
    defaults: dict[int, str] = {}
    for path, cid in paths.items():
        if path in DEFAULT_NATURES and cid not in defaults:
            defaults[cid] = DEFAULT_NATURES[path]

    def direct(cid: int) -> str | None:
        n = own.get(cid)
        return n if n in NATURES else defaults.get(cid)

    out = {}
    for cid in own:
        n = direct(cid)
        parent = parents.get(cid)
        if n is None and parent is not None:
            n = direct(parent)
        out[cid] = n or "essentiel"
    return out


def monthly_estimate(totals: list[int], nature: str) -> int:
    """Montant mensuel attendu d'après les mois passés (du plus ancien au plus récent).

    Dépenses courantes : médiane des 3 derniers mois (un mois exceptionnel ne fausse rien).
    Charges hors récurrents (factures irrégulières, impôts…) : moyenne des 6 derniers mois (lisse les factures
    trimestrielles ou annuelles, que la médiane ferait disparaître)."""
    if not totals:
        return 0
    if nature == "fixe":
        recent = totals[-6:]
        return round(sum(recent) / len(recent))
    return round(median(totals[-3:]))
