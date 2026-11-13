"""Couches de dépenses : nature des catégories et estimations mensuelles (sans base)."""

from app.layers import effective_natures, monthly_estimate


def test_effective_natures():
    paths = {"Alimentation": 1, "Alimentation/Courses": 2, "Alimentation/Livraison": 3, "Logement": 4, "Logement/Loyer / crédit": 5, "Tabac": 6, "Tabac/Cigarettes": 7}
    parents = {1: None, 2: 1, 3: 1, 4: None, 5: 4, 6: None, 7: 6}
    own = {1: None, 2: None, 3: None, 4: None, 5: None, 6: "plaisir", 7: None}
    n = effective_natures(own, parents, paths)
    assert n == {1: "essentiel", 2: "essentiel", 3: "plaisir", 4: "fixe", 5: "fixe", 6: "plaisir", 7: "plaisir"}
    # Réglage de l'utilisateur prioritaire ; catégorie inconnue sans parent : essentiel.
    own[2] = "plaisir"
    assert effective_natures(own | {8: None}, parents | {8: None}, paths)[2] == "plaisir"
    assert effective_natures(own | {8: None}, parents | {8: None}, paths)[8] == "essentiel"


def test_monthly_estimate():
    # Dépenses courantes : médiane des 3 derniers mois (un gros mois isolé ne compte pas).
    assert monthly_estimate([10000, 40000, 30000, 31000, 90000], "essentiel") == 31000
    # Charges irrégulières : moyenne des 6 derniers mois (facture trimestrielle lissée).
    assert monthly_estimate([0, 0, 30000, 0, 0, 30000], "fixe") == 10000
    assert monthly_estimate([], "plaisir") == 0
