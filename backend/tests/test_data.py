"""Page Vendeurs + réinitialisations, sur des données inventées."""

import pytest

from tests.test_import_ca import ROWS, make_csv
from tests.test_paypal import CA_ROWS, make_paypal


def _upload(client, source, data, account_id):
    return client.post(
        f"/api/imports/{source}", files={"file": ("x.csv", data, "text/csv")}, data={"account_id": str(account_id)}
    ).json()


@pytest.fixture
def ca(auth_client):
    acc = auth_client.post("/api/accounts", json={"name": "CA", "type": "courant"}).json()
    _upload(auth_client, "credit-agricole", make_csv(ROWS, number="44440000111"), acc["id"])
    return acc


def _merchants(client, **params):
    return {m["name"]: m for m in client.get("/api/merchants", params=params).json()}


def test_merchant_stats_and_period(auth_client, ca):
    ms = _merchants(auth_client)
    assert ms["Monoprix"]["count"] == 2 and ms["Monoprix"]["spent_cents"] == 1230 + 450
    assert ms["Acme Corp"]["received_cents"] == 202582 and ms["Acme Corp"]["spent_cents"] == 0
    # Les virements internes ne comptent ni en dépense ni en revenu.
    internal = next(m for m in ms.values() if "dupont" in m["name"].lower())
    assert internal["spent_cents"] == 0
    # Période : seules les opérations du 10/11 et après.
    ms2 = _merchants(auth_client, date_from="2026-11-10")
    assert ms2["Monoprix"]["count"] == 1 and ms2["Monoprix"]["spent_cents"] == 1230
    assert "Acme Corp" not in ms2  # rien sur la période → masqué


def test_choose_and_reset_merchant_category(auth_client, ca):
    cats = {c["name"]: c["id"] for c in auth_client.get("/api/categories").json()}
    acme = _merchants(auth_client)["Acme Corp"]
    assert acme["category_id"] is None and acme["category_chosen"] is False
    auth_client.post(f"/api/merchants/{acme['id']}/category", json={"category_id": cats["Salaire"]})
    acme = _merchants(auth_client)["Acme Corp"]
    assert acme["category_id"] == cats["Salaire"] and acme["category_chosen"] is True
    auth_client.post(f"/api/merchants/{acme['id']}/reset")
    acme = _merchants(auth_client)["Acme Corp"]
    assert acme["category_id"] is None and acme["category_chosen"] is False


def test_rename_and_merge(auth_client, ca):
    cats = {c["name"]: c["id"] for c in auth_client.get("/api/categories").json()}
    ms = _merchants(auth_client)
    bar = ms["Bar du Coin Paris"]
    auth_client.post(f"/api/merchants/{bar['id']}/category", json={"category_id": cats["Bars"]})
    r = auth_client.patch(f"/api/merchants/{bar['id']}", json={"name": "Bar du Coin"}).json()
    assert r["name"] == "Bar du Coin" and r["merged"] is False
    ms = _merchants(auth_client)
    assert ms["Bar du Coin"]["category_chosen"] is True  # la règle suit le nouveau nom

    # Renommer vers un nom existant = fusion.
    r = auth_client.patch(f"/api/merchants/{ms['Monoprix']['id']}", json={"name": "Bar du Coin"}).json()
    assert r["merged"] is True
    ms = _merchants(auth_client)
    assert "Monoprix" not in ms and ms["Bar du Coin"]["count"] == 4
    tx = auth_client.get("/api/transactions", params={"merchant_id": ms["Bar du Coin"]["id"]}).json()
    assert tx["total"] == 4


def test_undo_import(auth_client, ca):
    imports = auth_client.get("/api/data/imports").json()
    assert imports[0]["rows_imported"] == 10 and imports[0]["account_name"] == "CA"
    assert auth_client.delete(f"/api/data/imports/{imports[0]['id']}").json()["updated"] == 10
    assert auth_client.get("/api/transactions").json()["total"] == 0
    assert auth_client.get("/api/data/imports").json() == []


def test_clear_paypal_account_detaches_bank_side(auth_client):
    bank = auth_client.post("/api/accounts", json={"name": "CA", "type": "courant"}).json()
    pay = auth_client.post("/api/accounts", json={"name": "PayPal", "type": "paypal"}).json()
    _upload(auth_client, "credit-agricole", make_csv(CA_ROWS, number="44440000222"), bank["id"])
    assert _upload(auth_client, "paypal", make_paypal(), pay["id"])["reconciled"] == 1

    assert auth_client.post(f"/api/data/accounts/{pay['id']}/clear").json()["updated"] == 4
    row = next(t for t in auth_client.get("/api/transactions", params={"account_id": bank["id"]}).json()["items"] if t["amount_cents"] == -1230)
    assert row["merchant"] == "PayPal" and row["linked_id"] is None and not (row["details"] or {}).get("via")
    # Réimporter PayPal refait le rapprochement (le vidage n'interdit pas de re-rapprocher).
    assert _upload(auth_client, "paypal", make_paypal(), pay["id"])["reconciled"] == 1

    assert auth_client.delete(f"/api/data/accounts/{pay['id']}").status_code == 200
    assert all(a["id"] != pay["id"] for a in auth_client.get("/api/accounts", params={"include_archived": True}).json())


def test_reset_category_and_all(auth_client, ca):
    cats = {c["name"]: c["id"] for c in auth_client.get("/api/categories").json()}
    acme = _merchants(auth_client)["Acme Corp"]
    auth_client.post(f"/api/merchants/{acme['id']}/category", json={"category_id": cats["Salaire"]})
    auth_client.post(f"/api/data/categories/{cats['Revenus']}/reset")  # la catégorie parente inclut ses enfants
    assert _merchants(auth_client)["Acme Corp"]["category_chosen"] is False

    auth_client.post(f"/api/merchants/{acme['id']}/category", json={"category_id": cats["Salaire"]})
    auth_client.post("/api/data/reset-categorization")
    assert auth_client.get("/api/rules").json() == []


def test_wipe_needs_confirmation(auth_client, ca):
    assert auth_client.post("/api/data/wipe", json={"confirm": "oui"}).status_code == 422
    assert auth_client.post("/api/data/wipe", json={"confirm": "EFFACER", "keep_accounts": True}).status_code == 200
    assert auth_client.get("/api/transactions").json()["total"] == 0
    assert any(a["name"] == "CA" for a in auth_client.get("/api/accounts").json())
    assert auth_client.get("/api/merchants").json() == []
