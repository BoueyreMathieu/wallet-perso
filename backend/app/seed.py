"""Données par défaut (catégories, règles), versionnées.

Chaque jeu a un numéro de version stocké dans app_meta. Au démarrage, si la version en base
est plus ancienne, on complète :
- catégories : on ajoute celles qui manquent, sauf celles que tu as supprimées ou renommées ;
- règles : on remplace les règles par défaut, sans toucher à celles créées par tes corrections.
"""

import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.default_rules import DEFAULT_RULES
from app.models import AppMeta, Category, Rule

CATEGORIES_VERSION = 5
RULES_VERSION = 3

# (nom, type, couleur, sous-catégories)
DEFAULT_CATEGORIES: list[tuple[str, str, str, list[str]]] = [
    ("Alimentation", "depense", "#16a34a", [
        "Courses", "Restaurants", "Fast-food", "Livraison", "Boulangerie / café", "Cantine / tickets resto", "Cave / alcool",
    ]),
    ("Logement", "depense", "#60a5fa", [
        "Loyer / crédit", "Charges / syndic", "Énergie", "Eau", "Internet / téléphone", "Assurance habitation",
        "Taxes locales", "Travaux / maison", "Ameublement / déco", "Électroménager",
    ]),
    ("Transport", "depense", "#22d3ee", [
        "Carburant", "Transports en commun", "Train / avion", "Taxi / VTC", "Vélo / trottinette", "Péage / parking",
        "Entretien véhicule", "Assurance auto", "Location véhicule",
    ]),
    ("Abonnements", "depense", "#8b5cf6", [
        "Streaming", "Musique", "Jeux en ligne", "Logiciels / cloud", "Presse", "Salle de sport",
    ]),
    ("Loisirs", "depense", "#f472b6", [
        "Sorties", "Bars", "Cinéma", "Concerts / spectacles", "Voyages", "Sport", "Jeux / culture", "Livres / BD",
        "Hobbies / créatif",
    ]),
    ("Shopping", "depense", "#f97316", [
        "Achats en ligne", "Vêtements", "Chaussures / accessoires", "High-tech", "Maison", "Cadeaux",
    ]),
    ("Santé", "depense", "#ef4444", [
        "Médecin", "Pharmacie", "Mutuelle", "Dentiste", "Optique", "Paramédical", "Analyses / hôpital",
    ]),
    ("Beauté & soins", "depense", "#d946ef", ["Coiffeur", "Cosmétiques", "Soins / esthétique"]),
    ("Banque & impôts", "depense", "#475569", [
        "Frais bancaires", "Impôts", "Intérêts d'emprunt", "Remboursement de crédit", "Retraits d'espèces", "Amendes",
    ]),
    ("Assurances", "depense", "#0f766e", ["Prévoyance / vie", "Assurance emprunteur", "Autres assurances"]),
    ("Éducation & formation", "depense", "#4338ca", ["Formation", "Fournitures", "Frais de scolarité"]),
    ("Animaux", "depense", "#92400e", ["Nourriture / accessoires", "Vétérinaire", "Garde / toilettage"]),
    ("Dons & associations", "depense", "#fbbf24", ["Dons", "Cotisations associatives", "Cagnottes"]),
    ("Famille & amis", "depense", "#a3e635", ["Remboursements à des proches", "Aide familiale", "Enfants"]),
    ("Travail", "depense", "#0369a1", ["Frais professionnels", "Avances à se faire rembourser"]),
    ("Divers", "depense", "#a8a29e", ["Autres dépenses", "Imprévus"]),
    ("Revenus", "revenu", "#059669", [
        "Salaire", "Primes / épargne salariale", "Freelance / missions", "Remboursements", "Remboursements santé",
        "Remboursements de proches", "Aides / allocations", "Intérêts / dividendes", "Ventes", "Autres revenus",
    ]),
    ("Transferts", "transfert", "#94a3b8", ["Virement interne", "Épargne / investissement", "PayPal"]),
]

# Couleurs par défaut avant la version 5 (trop proches entre elles) : remplacées si tu ne les as pas changées.
OLD_DEFAULT_COLORS: dict[str, str] = {
    "Alimentation": "#16a34a",
    "Logement": "#2563eb",
    "Transport": "#0891b2",
    "Abonnements": "#7c3aed",
    "Loisirs": "#db2777",
    "Shopping": "#ea580c",
    "Santé": "#dc2626",
    "Beauté & soins": "#c026d3",
    "Banque & impôts": "#525252",
    "Assurances": "#0f766e",
    "Éducation & formation": "#4f46e5",
    "Animaux": "#a16207",
    "Dons & associations": "#be123c",
    "Famille & amis": "#e11d48",
    "Travail": "#334155",
    "Divers": "#78716c",
    "Revenus": "#059669",
    "Transferts": "#64748b",
}

INTERNAL_TRANSFER_PATH = "Transferts/Virement interne"
# Catégories indispensables au fonctionnement (détection des virements internes) : non supprimables.
PROTECTED_PATHS = {"Transferts", INTERNAL_TRANSFER_PATH}

# Icônes par défaut (une sous-catégorie sans icône prend celle de sa catégorie).
DEFAULT_ICONS: dict[str, str] = {
    "Alimentation": "🛒", "Alimentation/Courses": "🛒", "Alimentation/Restaurants": "🍽️", "Alimentation/Fast-food": "🍔",
    "Alimentation/Livraison": "🛵", "Alimentation/Boulangerie / café": "🥐", "Alimentation/Cantine / tickets resto": "🍱",
    "Alimentation/Cave / alcool": "🍷",
    "Logement": "🏠", "Logement/Loyer / crédit": "🔑", "Logement/Énergie": "⚡", "Logement/Eau": "💧",
    "Logement/Internet / téléphone": "📶", "Logement/Travaux / maison": "🔨", "Logement/Ameublement / déco": "🛋️",
    "Transport": "🚗", "Transport/Carburant": "⛽", "Transport/Transports en commun": "🚇", "Transport/Train / avion": "✈️",
    "Transport/Taxi / VTC": "🚕", "Transport/Vélo / trottinette": "🚲", "Transport/Péage / parking": "🅿️",
    "Abonnements": "🔁", "Abonnements/Streaming": "📺", "Abonnements/Musique": "🎧", "Abonnements/Jeux en ligne": "🎮",
    "Abonnements/Logiciels / cloud": "☁️", "Abonnements/Presse": "📰", "Abonnements/Salle de sport": "🏋️",
    "Loisirs": "🎉", "Loisirs/Bars": "🍻", "Loisirs/Cinéma": "🎬", "Loisirs/Concerts / spectacles": "🎤",
    "Loisirs/Voyages": "🧳", "Loisirs/Sport": "⚽", "Loisirs/Jeux / culture": "🎲", "Loisirs/Livres / BD": "📚",
    "Loisirs/Hobbies / créatif": "🎨",
    "Shopping": "🛍️", "Shopping/Achats en ligne": "📦", "Shopping/Vêtements": "👕", "Shopping/Chaussures / accessoires": "👟",
    "Shopping/High-tech": "💻", "Shopping/Cadeaux": "🎁",
    "Santé": "🩺", "Santé/Pharmacie": "💊", "Santé/Dentiste": "🦷", "Santé/Optique": "👓",
    "Beauté & soins": "💅", "Beauté & soins/Coiffeur": "💇",
    "Banque & impôts": "🏦", "Banque & impôts/Impôts": "🧾", "Banque & impôts/Retraits d'espèces": "💶",
    "Assurances": "🛡️",
    "Éducation & formation": "🎓",
    "Animaux": "🐾",
    "Dons & associations": "🤝",
    "Famille & amis": "👨‍👩‍👧",
    "Travail": "💼",
    "Divers": "📌",
    "Revenus": "💰", "Revenus/Salaire": "💶", "Revenus/Remboursements": "↩️", "Revenus/Intérêts / dividendes": "📈",
    "Revenus/Ventes": "🏷️",
    "Transferts": "🔄", "Transferts/Épargne / investissement": "🐷", "Transferts/PayPal": "🅿️",
}


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


def hidden_defaults(db: Session) -> set[str]:
    """Chemins de catégories par défaut supprimées par l'utilisateur : ne jamais les recréer."""
    return set(json.loads(get_meta(db, "hidden_default_categories", "[]")))


def category_aliases(db: Session) -> dict[str, int]:
    """Ancien chemin → id, pour les catégories renommées ou déplacées par l'utilisateur."""
    return {k: int(v) for k, v in json.loads(get_meta(db, "category_aliases", "{}")).items()}


def resolve_paths(db: Session) -> dict[str, int]:
    """Chemins actuels + anciens chemins (renommages) encore valides."""
    paths = category_paths(db)
    ids = set(paths.values())
    for old, cid in category_aliases(db).items():
        if old not in paths and cid in ids:
            paths[old] = cid
    return paths


def ensure_categories(db: Session) -> int:
    if int(get_meta(db, "categories_version", "0")) >= CATEGORIES_VERSION:
        return 0
    paths = resolve_paths(db)
    hidden = hidden_defaults(db)
    created = 0
    for name, kind, color, children in DEFAULT_CATEGORIES:
        if name in hidden:
            continue
        if name not in paths:
            parent = Category(name=name, kind=kind, color=color, icon=DEFAULT_ICONS.get(name))
            db.add(parent)
            db.flush()
            paths[name] = parent.id
            created += 1
        for child in children:
            path = f"{name}/{child}"
            if path not in paths and path not in hidden:
                db.add(Category(name=child, kind=kind, color=color, parent_id=paths[name], icon=DEFAULT_ICONS.get(path)))
                created += 1
    # Nouvelle palette (v5) : catégories principales encore à leur ancienne couleur par défaut → nouvelle couleur ;
    # leurs sous-catégories de la même couleur suivent (l'interface les nuance automatiquement).
    new_by_name = {name: color for name, _, color, _ in DEFAULT_CATEGORIES}
    for name, old in OLD_DEFAULT_COLORS.items():
        cat = db.get(Category, paths[name]) if name in paths else None
        if cat is None or cat.parent_id is not None or (cat.color or "").lower() != old or name not in new_by_name:
            continue
        cat.color = new_by_name[name]
        for child in db.scalars(select(Category).where(Category.parent_id == cat.id)):
            if (child.color or "").lower() == old:
                child.color = cat.color
    # Icônes par défaut sur les catégories existantes qui n'en ont pas encore.
    for path, icon in DEFAULT_ICONS.items():
        cat = db.get(Category, paths[path]) if path in paths else None
        if cat is not None and not cat.icon:
            cat.icon = icon
    set_meta(db, "categories_version", str(CATEGORIES_VERSION))
    db.flush()
    return created


def ensure_rules(db: Session) -> int:
    if int(get_meta(db, "rules_version", "0")) >= RULES_VERSION:
        return 0
    paths = resolve_paths(db)
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
