"""Catégories par défaut, créées au premier démarrage."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category

# (nom, type, couleur, sous-catégories)
DEFAULT_CATEGORIES: list[tuple[str, str, str, list[str]]] = [
    ("Alimentation", "depense", "#16a34a", ["Courses", "Restaurants", "Livraison", "Boulangerie / café"]),
    ("Logement", "depense", "#2563eb", ["Loyer / crédit", "Énergie", "Eau", "Internet / téléphone", "Assurance habitation", "Travaux / maison"]),
    ("Transport", "depense", "#0891b2", ["Carburant", "Transports en commun", "Péage / parking", "Entretien véhicule", "Assurance auto", "Train / avion"]),
    ("Abonnements", "depense", "#7c3aed", ["Streaming", "Logiciels / cloud", "Presse", "Salle de sport"]),
    ("Loisirs", "depense", "#db2777", ["Sorties", "Voyages", "Sport", "Jeux / culture"]),
    ("Shopping", "depense", "#ea580c", ["Vêtements", "High-tech", "Maison", "Cadeaux"]),
    ("Santé", "depense", "#dc2626", ["Médecin", "Pharmacie", "Mutuelle"]),
    ("Banque & impôts", "depense", "#525252", ["Frais bancaires", "Impôts", "Intérêts d'emprunt"]),
    ("Revenus", "revenu", "#059669", ["Salaire", "Remboursements", "Intérêts / dividendes", "Ventes", "Autres revenus"]),
    ("Transferts", "transfert", "#64748b", ["Virement interne", "Épargne / investissement"]),
    ("Non catégorisé", "depense", "#a3a3a3", []),
]


def seed_categories(db: Session) -> int:
    """Crée les catégories par défaut si la table est vide. Retourne le nombre créé."""
    if db.scalar(select(Category.id).limit(1)) is not None:
        return 0
    created = 0
    for name, kind, color, children in DEFAULT_CATEGORIES:
        parent = Category(name=name, kind=kind, color=color)
        db.add(parent)
        db.flush()
        created += 1
        for child in children:
            db.add(Category(name=child, kind=kind, color=color, parent_id=parent.id))
            created += 1
    db.commit()
    return created
