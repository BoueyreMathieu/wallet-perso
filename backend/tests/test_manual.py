"""Opérations saisies à la main, solde calculé, fusion avec un import (données inventées)."""

from datetime import date

from tests.test_import_ca import ROWS, make_csv

TODAY = date.today().isoformat()


def _balance(client, account_id):
    return next(a for a in client.get("/api/accounts").json() if a["id"] == account_id)["balance_cents"]


def test_manual_operation_changes_balance(auth_client):
    c = auth_client
    cash = c.post("/api/accounts", json={"name": "Espèces", "type": "especes", "initial_balance_cents": 10000}).json()
    r = c.post(
        "/api/transactions",
        json={"account_id": cash["id"], "booked_at": TODAY, "amount_cents": -2500, "label": "Pain et croissants", "merchant": "Boulangerie Test"},
    )
    assert r.status_code == 201, r.text
    tx = r.json()
    assert tx["merchant"] == "Boulangerie Test" and tx["category_id"] is not None  # règle « BOULANGERIE »
    assert _balance(c, cash["id"]) == 7500
    assert c.get("/api/accounts/net-worth").json()["by_type"]["especes"] == 7500

    # Modifier le montant met le solde à jour ; supprimer l'opération le rétablit.
    c.patch(f"/api/transactions/{tx['id']}", json={"amount_cents": -4000})
    assert _balance(c, cash["id"]) == 6000
    assert c.delete(f"/api/transactions/{tx['id']}").status_code == 200
    assert _balance(c, cash["id"]) == 10000

    assert c.post("/api/transactions", json={"account_id": cash["id"], "booked_at": TODAY, "amount_cents": 0, "label": "x"}).status_code == 422


def test_balance_counts_only_operations_after_known_balance(auth_client):
    c = auth_client
    acc = c.post("/api/accounts", json={"name": "Livret", "type": "epargne"}).json()
    c.post(f"/api/accounts/{acc['id']}/balances", json={"date": "2026-11-10", "balance_cents": 50000})
    c.post("/api/transactions", json={"account_id": acc["id"], "booked_at": "2026-11-01", "amount_cents": -1000, "label": "avant"})
    assert _balance(c, acc["id"]) == 50000  # déjà inclus dans le solde du 10/11
    c.post("/api/transactions", json={"account_id": acc["id"], "booked_at": "2026-11-12", "amount_cents": 2500, "label": "après"})
    assert _balance(c, acc["id"]) == 52500


def test_imported_operations_cannot_be_edited_like_manual_ones(auth_client):
    c = auth_client
    acc = c.post("/api/accounts", json={"name": "CA", "type": "courant"}).json()
    c.post("/api/imports/credit-agricole", files={"file": ("x.csv", make_csv(ROWS, number="66660000111"), "text/csv")}, data={"account_id": str(acc["id"])})
    imported = c.get("/api/transactions", params={"account_id": acc["id"]}).json()["items"][0]
    assert c.patch(f"/api/transactions/{imported['id']}", json={"amount_cents": -1}).status_code == 422
    # …mais la note et la catégorie restent modifiables.
    assert c.patch(f"/api/transactions/{imported['id']}", json={"note": "ok"}).status_code == 200


def test_manual_entry_merged_with_later_import(auth_client):
    c = auth_client
    cats = {x["name"]: x["id"] for x in c.get("/api/categories").json()}
    tag = c.post("/api/tags", json={"name": "Perso"}).json()
    acc = c.post("/api/accounts", json={"name": "CA", "type": "courant"}).json()
    manual = c.post(
        "/api/transactions",
        json={
            "account_id": acc["id"], "booked_at": "2026-11-09", "amount_cents": -1230, "label": "Courses du soir",
            "category_id": cats["Restaurants"], "note": "avec Paul", "tag_ids": [tag["id"]],
        },
    ).json()

    res = c.post(
        "/api/imports/credit-agricole",
        files={"file": ("x.csv", make_csv(ROWS, number="66660000222"), "text/csv")},
        data={"account_id": str(acc["id"])},
    ).json()
    assert res["merged_manual"] == 1

    items = c.get("/api/transactions", params={"account_id": acc["id"]}).json()["items"]
    assert len(items) == 10 and all(t["id"] != manual["id"] for t in items)
    merged = next(t for t in items if t["amount_cents"] == -1230)
    assert merged["category_id"] == cats["Restaurants"] and merged["category_locked"] is True
    assert merged["note"] == "avec Paul" and merged["tags"][0]["name"] == "Perso"
    assert _balance(c, acc["id"]) == 123456  # solde de l'export, sans double comptage


def test_no_merchant_filter(auth_client):
    c = auth_client
    acc = c.post("/api/accounts", json={"name": "Espèces", "type": "especes"}).json()
    c.post("/api/transactions", json={"account_id": acc["id"], "booked_at": TODAY, "amount_cents": -100, "label": "sans vendeur"})
    c.post("/api/transactions", json={"account_id": acc["id"], "booked_at": TODAY, "amount_cents": -200, "label": "avec", "merchant": "Kiosque"})
    items = c.get("/api/transactions", params={"no_merchant": True}).json()["items"]
    assert [t["raw_label"] for t in items] == ["sans vendeur"]
