"""Import PayPal + rapprochement avec le compte bancaire, sur des données inventées."""

import csv
import io

import pytest

from app.importers import paypal as pp
from tests.test_import_ca import _row, make_csv

COLS = [
    "Date", "Heure", "Fuseau horaire", "Nom", "Type", "État", "Devise", "Avant commission", "Commission", "Net",
    "De l'adresse email", "À l'adresse email", "Numéro de transaction", "Titre de l'objet",
    "Numéro de la transaction de référence", "Solde", "Objet", "Impact sur le solde",
]
PURCHASE = "Paiement préapprouvé d'un utilisateur de facture de paiement"
FUNDING = "Virement bancaire sur le compte PayPal"


def pp_row(date, heure, nom, typ, etat, net, txid, ref="", objet="", solde="0,00", impact="Débit"):
    return {
        "Date": date, "Heure": heure, "Fuseau horaire": "CET", "Nom": nom, "Type": typ, "État": etat,
        "Devise": "EUR", "Avant commission": net, "Commission": "0,00", "Net": net,
        "De l'adresse email": "moi@example.com" if impact == "Débit" else "", "À l'adresse email": "shop@example.com",
        "Numéro de transaction": txid, "Titre de l'objet": objet, "Numéro de la transaction de référence": ref,
        "Solde": solde, "Objet": objet, "Impact sur le solde": impact,
    }


ROWS = [
    pp_row("01/11/2026", "10:00:00", "Pizza Roma", PURCHASE, "Terminé", "-12,30", "1P1", "B-AUTH1", "Commande 42", "-12,30"),
    pp_row("01/11/2026", "10:00:01", "", FUNDING, "En attente", "12,30", "1F1", "1P1", "", "0,00", "Crédit"),
    pp_row("01/11/2026", "09:59:00", "Pizza Roma", "Autorisation standard", "En attente", "-12,30", "AUTH1", "", "", "0,00", "Mémo"),
    pp_row("02/11/2026", "08:00:00", "Ciné Club", "Paiement Express Checkout", "Terminé", "-5,00", "1P2", "", "Place", "-5,00"),
    pp_row("02/11/2026", "08:30:00", "Hotel X", "Suspension de compte pour autorisation en cours", "En attente", "-50,00", "1S1", "AUTH2"),
    pp_row("03/11/2026", "08:30:00", "Hotel X", "Annulation de suspension de compte standard", "Terminé", "50,00", "1S2", "1S1", "", "0,00", "Crédit"),
    pp_row("04/11/2026", "12:00:00", "Un Ami", "Paiements groupés", "Terminé", "20,00", "1G1", "", "Remboursement", "15,00", "Crédit"),
]


def make_paypal(rows=ROWS) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS, quoting=csv.QUOTE_ALL)
    w.writeheader()
    w.writerows(rows)
    return ("﻿" + buf.getvalue()).encode("utf-8")


# --- Parser (sans base) ---------------------------------------------------------


def test_parse_keeps_real_movements_only():
    st = pp.parse(make_paypal())
    by_id = {t.external_id: t for t in st.transactions}
    assert set(by_id) == {"1P1", "1F1", "1P2", "1G1"}  # autorisation et suspensions ignorées
    assert by_id["1P1"].amount_cents == -1230 and by_id["1P1"].merchant_hint == "Pizza Roma"
    assert by_id["1P1"].details["objet"] == "Commande 42"
    f = by_id["1F1"]
    assert f.details["role"] == "approvisionnement" and f.details["reference"] == "1P1"
    assert f.counted is False and f.force_category_path == "Transferts/PayPal" and f.merchant_hint is None
    assert st.balance_cents == 1500  # solde de la dernière opération
    assert st.account_external_id.startswith("paypal:") and "example" not in st.account_external_id
    # Aucune donnée personnelle conservée
    assert all("@" not in str(t.details) for t in st.transactions)


def test_parse_rejects_other_files():
    with pytest.raises(pp.PayPalParseError):
        pp.parse(b"a,b\n1,2\n")


# --- Rapprochement via l'API -----------------------------------------------------

CA_ROWS = [
    _row("03/11/2026", ["Prélèvement", "PayPal Europe S.a.r.l. et Cie S. - PayPal - 123/PAYPAL", "", "M1", "LU96ZZZ0000000000000000058", "123"], "12,30"),
    _row("02/11/2026", ["Paiement par carte", "X1234 MONOP PARIS 01/11"], "8,00"),
]


def _upload(client, source, data, account_id=None):
    form = {"account_id": str(account_id)} if account_id else {}
    return client.post(f"/api/imports/{source}", files={"file": ("x.csv", data, "text/csv")}, data=form)


@pytest.fixture
def accounts(auth_client):
    ca = auth_client.post("/api/accounts", json={"name": "CA", "type": "courant"}).json()
    pay = auth_client.post("/api/accounts", json={"name": "PayPal", "type": "paypal"}).json()
    return ca, pay


def _tx(client, **params):
    return client.get("/api/transactions", params=params).json()["items"]


def test_paypal_reconciliation(auth_client, accounts):
    ca, pay = accounts
    cats = {c["name"]: c["id"] for c in auth_client.get("/api/categories").json()}

    assert _upload(auth_client, "credit-agricole", make_csv(CA_ROWS, number="77770000111"), ca["id"]).status_code == 200
    # Un compte non-PayPal est refusé pour un export PayPal.
    assert _upload(auth_client, "paypal", make_paypal(), ca["id"]).status_code == 422
    res = _upload(auth_client, "paypal", make_paypal(), pay["id"]).json()
    assert res["imported"] == 4 and res["reconciled"] == 1

    bank = next(t for t in _tx(auth_client, account_id=ca["id"]) if t["amount_cents"] == -1230)
    assert bank["merchant"] == "Pizza Roma"
    assert bank["category_id"] == cats["Restaurants"]  # catégorie de l'achat réel, pas « Achats en ligne »
    assert bank["details"]["via"] == "PayPal" and bank["details"]["objet"] == "Commande 42"
    assert bank["counted"] is True and bank["is_transfer"] is False

    pp_items = {t["details"]["transaction"]: t for t in _tx(auth_client, account_id=pay["id"])}
    purchase, funding = pp_items["1P1"], pp_items["1F1"]
    assert purchase["linked_id"] == bank["id"] and purchase["counted"] is False
    assert funding["is_transfer"] is True and funding["counted"] is False
    assert pp_items["1P2"]["counted"] is True  # payé avec le solde PayPal : vraie dépense côté PayPal

    # Changer la catégorie d'un côté met l'autre à jour.
    auth_client.patch(f"/api/transactions/{bank['id']}", json={"category_id": cats["Livraison"]})
    purchase = next(t for t in _tx(auth_client, account_id=pay["id"]) if t["id"] == purchase["id"])
    assert purchase["category_id"] == cats["Livraison"]

    # Réimport : rien de nouveau, rien de rapproché deux fois.
    res2 = _upload(auth_client, "paypal", make_paypal()).json()
    assert res2["imported"] == 0 and res2["reconciled"] == 0 and res2["account_id"] == pay["id"]

    # Dissocier : la ligne bancaire redevient un prélèvement PayPal, l'achat recompte.
    assert auth_client.post(f"/api/transactions/{bank['id']}/unlink").status_code == 200
    bank2 = next(t for t in _tx(auth_client, account_id=ca["id"]) if t["id"] == bank["id"])
    assert bank2["merchant"] == "PayPal" and bank2["linked_id"] is None and "via" not in (bank2["details"] or {})
    purchase2 = next(t for t in _tx(auth_client, account_id=pay["id"]) if t["id"] == purchase["id"])
    assert purchase2["counted"] is True and purchase2["linked_id"] is None


def test_reconciliation_works_in_any_order(auth_client, accounts):
    ca, pay = accounts
    _upload(auth_client, "paypal", make_paypal(), pay["id"])
    res = _upload(auth_client, "credit-agricole", make_csv(CA_ROWS, number="77770000222"), ca["id"]).json()
    assert res["reconciled"] == 1


def test_ambiguous_match_is_not_guessed(auth_client, accounts):
    ca, pay = accounts
    rows = ROWS + [
        pp_row("01/11/2026", "11:00:00", "Autre Resto", PURCHASE, "Terminé", "-12,30", "1P3", "", "", "-12,30"),
        pp_row("01/11/2026", "11:00:01", "", FUNDING, "En attente", "12,30", "1F3", "1P3", "", "0,00", "Crédit"),
    ]
    _upload(auth_client, "paypal", make_paypal(rows), pay["id"])
    res = _upload(auth_client, "credit-agricole", make_csv(CA_ROWS, number="77770000333"), ca["id"]).json()
    assert res["reconciled"] == 0
