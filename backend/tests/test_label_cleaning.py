"""Extraction du vendeur depuis un libellé bancaire (pur Python, libellés inventés)."""

from app.label_cleaning import clean_payee, is_generic


def test_card_payments():
    assert clean_payee("PAIEMENT PAR CARTE X1234 MONOP PARIS 01/11") == "MONOP PARIS"
    assert clean_payee("Paiement par carte X9876 BOULANGERIE DU COIN 15/10/26") == "BOULANGERIE DU COIN"
    assert clean_payee("CB CARREFOUR MARKET 4973XXXXXXXX1234 12/11") == "CARREFOUR MARKET"
    assert clean_payee("PAIEMENT PAR CARTE X1234 01/11") == ""


def test_transfers_and_debits():
    assert clean_payee("VIREMENT EMIS VERS MONSIEUR TESTEUR JEAN") == "MONSIEUR TESTEUR JEAN"
    assert clean_payee("VIREMENT EN VOTRE FAVEUR DE ACME SAS") == "ACME SAS"
    assert clean_payee("VIR SEPA RECU DE MADAME EXEMPLE") == "MADAME EXEMPLE"
    assert clean_payee("PRLV SEPA FOURNISSEUR ENERGIE REF123456") == "FOURNISSEUR ENERGIE"
    assert clean_payee("Prélèvement Échéance Assurance Truc") == "Assurance Truc"
    assert clean_payee("RETRAIT DAB 12/11 PARIS") == "Retrait d'espèces"


def test_is_generic():
    assert is_generic("Paiement Par Carte X1234 Monop")
    assert is_generic("Virement Emis Vers Monsieur Testeur")
    assert is_generic("VIREMENT EN VOTRE FAVEUR")
    assert not is_generic("Carrefour Market")
    assert not is_generic("Cartes Grises Express")  # « CARTE » doit être un mot entier
    assert not is_generic("Carte Grise Express")  # mot seul non suivi d'un n° de carte ou d'une date
    assert not is_generic("Cheque Dejeuner")
    assert not is_generic("Achat Malin")
    assert clean_payee("RETRAITE COMPLEMENTAIRE") == "RETRAITE COMPLEMENTAIRE"
    assert not is_generic("Virementix")
    assert not is_generic("")
