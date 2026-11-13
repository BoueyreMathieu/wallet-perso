"""Relation entre noms de vendeurs (pur Python, noms inventés)."""

from app.merchant_similarity import core, relation


def test_core_strips_trailing_references():
    assert core("Carrefour Market 1234") == "CARREFOUR MARKET"
    assert core("Monsieur Testeur Jean 12 X9") == "MONSIEUR TESTEUR JEAN"
    assert core("7 Eleven") == "7 ELEVEN"


def test_sure_matches():
    assert relation("MONSIEUR TESTEUR JEA", "Monsieur Testeur Jean") == "sure"  # troncature
    assert relation("Monsieur Testeur Jea", "MONSIEUR TESTEUR JEAN 12") == "sure"
    assert relation("Carrefour Market 1234", "CARREFOUR MARKET 5678") == "sure"
    assert relation("Boulangerie Dupain", "Boulangerie Dupain") == "sure"


def test_maybe_and_unrelated():
    assert relation("Monsieur Testeur Jean", "Monsieur Testeur Paul") == "maybe"
    assert relation("Carrefour Market", "Carrefour City") is None  # un seul mot en commun
    assert relation("SNCF", "SNCF Connect") is None  # trop court pour une troncature sûre
    assert relation("Amazon", "Netflix") is None
    assert relation("", "Amazon") is None


def test_bank_operation_prefixes_are_not_a_shared_name():
    assert relation("Paiement Par Carte X1234 Monop 01/11", "Paiement Par Carte X1234 Carrefour 02/11") is None
    assert relation("Virement Emis Vers Monsieur Testeur Jea", "Virement Emis Vers Madame Exemple") is None
    assert relation("Virement Emis Vers Monsieur Testeur Jea", "Monsieur Testeur Jean") == "sure"
    assert relation("Paiement Par Carte X1234 01/11", "Paiement Par Carte X5678 03/11") is None  # aucun vendeur
