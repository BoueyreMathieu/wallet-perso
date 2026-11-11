"""Données par défaut (catégories, règles), versionnées.

Chaque jeu a un numéro de version stocké dans app_meta. Au démarrage, si la version en base
est plus ancienne, on complète :
- catégories : on ajoute celles qui manquent (on ne supprime ni ne renomme rien) ;
- règles : on remplace les règles par défaut, sans toucher à celles créées par tes corrections.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.default_rules import DEFAULT_RULES
from app.models import AppMeta, Category, Rule

CATEGORIES_VERSION = 3
RULES_VERSION = 3

# (nom, type, couleur, sous-catégories)
DEFAULT_CATEGORIES: list[tuple[str, str, str, list[str]]] = [
    ("Alimentation", "depense", "#16a34a", [
        "Courses", "Restaurants", "Fast-food", "Livraison", "Boulangerie / café", "Cantine / tickets resto", "Cave / alcool",
    ]),
    ("Logement", "depense", "#2563eb", [
        "Loyer / crédit", "Charges / syndic", "Énergie", "Eau", "Internet / téléphone", "Assurance habitation",
        "Taxes locales", "Travaux / maison", "Ameublement / déco", "Électroménager",
    ]),
    ("Transport", "depense", "#0891b2", [
        "Carburant", "Transports en commun", "Train / avion", "Taxi / VTC", "Vélo / trottinette", "Péage / parking",
        "Entretien véhicule", "Assurance auto", "Location véhicule",
    ]),
    ("Abonnements", "depense", "#7c3aed", [
        "Streaming", "Musique", "Jeux en ligne", "Logiciels / cloud", "Presse", "Salle de sport",
    ]),
    ("Loisirs", "depense", "#db2777", [
        "Sorties", "Bars", "Cinéma", "Concerts / spectacles", "Voyages", "Sport", "Jeux / culture", "Livres / BD",
        "Hobbies / créatif",
    ]),
    ("Shopping", "depense", "#ea580c", [
        "Achats en ligne", "Vêtements", "Chaussures / accessoires", "High-tech", "Maison", "Cadeaux",
    ]),
    ("Santé", "depense", "#dc2626", [
        "Médecin", "Pharmacie", "Mutuelle", "Dentiste", "Optique", "Paramédical", "Analyses / hôpital",
    ]),
    ("Beauté & soins", "depense", "#c026d3", ["Coiffeur", "Cosmétiques", "Soins / esthétique"]),
    ("Banque & impôts", "depense", "#525252", [
        "Frais bancaires", "Impôts", "Intérêts d'emprunt", "Remboursement de crédit", "Retraits d'espèces", "Amendes",
    ]),
    ("Assurances", "depense", "#0f766e", ["Prévoyance / vie", "Assurance emprunteur", "Autres assurances"]),
    ("Éducation & formation", "depense", "#4f46e5", ["Formation", "Fournitures", "Frais de scolarité"]),
    ("Animaux", "depense", "#a16207", ["Nourriture / accessoires", "Vétérinaire", "Garde / toilettage"]),
    ("Dons & associations", "depense", "#be123c", ["Dons", "Cotisations associatives", "Cagnottes"]),
    ("Famille & amis", "depense", "#e11d48", ["Remboursements à des proches", "Aide familiale", "Enfants"]),
    ("Travail", "depense", "#334155", ["Frais professionnels", "Avances à se faire rembourser"]),
    ("Divers", "depense", "#78716c", ["Autres dépenses", "Imprévus"]),
    ("Revenus", "revenu", "#059669", [
        "Salaire", "Primes / épargne salariale", "Freelance / missions", "Remboursements", "Remboursements santé",
        "Remboursements de proches", "Aides / allocations", "Intérêts / dividendes", "Ventes", "Autres revenus",
    ]),
    ("Transferts", "transfert", "#64748b", ["Virement interne", "Épargne / investissement", "PayPal"]),
]

INTERNAL_TRANSFER_PATH = "Transferts/Virement interne"


def get_meta(db: Session, key: str, default: str | None = None) -> str | None:
    row = db.get(AppMeta, key)
    return row.value if row else default


def set_meta(db: Session, key: str, value: str) -> None:
    row = db.get(AppMeta, key)
    if row:
        row.value = value
    else:
        db.add(AppMeta(key=key, value=value))


def category_paths(db: Session) -> dict[str, int]:
    """{"Alimentation": 1, "Alimentation/Courses": 2, …}"""
    cats = db.scalars(select(Category)).all()
    by_id = {c.id: c for c in cats}
    paths = {}
    for c in cats:
        parent = by_id.get(c.parent_id) if c.parent_id else None
        paths[f"{parent.name}/{c.name}" if parent else c.name] = c.id
    return paths


def ensure_categories(db: Session) -> int:
    if int(get_meta(db, "categories_version", "0")) >= CATEGORIES_VERSION:
        return 0
    paths = category_paths(db)
    created = 0
    for name, kind, color, children in DEFAULT_CATEGORIES:
        if name not in paths:
            parent = Category(name=name, kind=kind, color=color)
            db.add(parent)
            db.flush()
            paths[name] = parent.id
            created += 1
        for child in children:
            if f"{name}/{child}" not in paths:
                db.add(Category(name=child, kind=kind, color=color, parent_id=paths[name]))
                created += 1
    set_meta(db, "categories_version", str(CATEGORIES_VERSION))
    db.flush()
    return created


def ensure_rules(db: Session) -> int:
    if int(get_meta(db, "rules_version", "0")) >= RULES_VERSION:
        return 0
    paths = category_paths(db)
    db.execute(delete(Rule).where(Rule.from_correction.is_(False)))
    created = 0
    for path, patterns, priority in DEFAULT_RULES:
        cat_id = paths.get(path)
        if cat_id is None:
            continue  # catégorie supprimée par l'utilisateur
        for p in patterns:
            db.add(Rule(pattern=p, match_type="contient", category_id=cat_id, priority=priority))
            created += 1
    set_meta(db, "rules_version", str(RULES_VERSION))
    return created


def seed_all(db: Session) -> None:
    ensure_categories(db)
    if ensure_rules(db):
        # Nouvelles règles par défaut : on les réapplique aux opérations existantes
        # (sans toucher à celles que tu as catégorisées à la main).
        from app.services.categorizing import recategorize

        db.flush()
        recategorize(db)
    db.commit()
