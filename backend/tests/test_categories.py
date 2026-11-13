"""Catégories personnalisées : création, modification, suppression (données inventées)."""

from datetime import date

TODAY = date.today().isoformat()


def _cats(c):
    return {(x["parent_id"], x["name"]): x for x in c.get("/api/categories").json()}


def _op(c, account_id, category_id, label="Opération Zxq", merchant="Vendeur Inventé Zeta"):
    r = c.post(
        "/api/transactions",
        json={"account_id": account_id, "booked_at": TODAY, "amount_cents": -1234, "label": label, "merchant": merchant, "category_id": category_id},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_rules_and_validation(auth_client):
    c = auth_client
    parent = c.post("/api/categories", json={"name": "Projet Test", "kind": "depense", "color": "#ff8800", "icon": "🧪"})
    assert parent.status_code == 201, parent.text
    p = parent.json()
    child = c.post("/api/categories", json={"name": "Matériel", "parent_id": p["id"]}).json()
    assert child["kind"] == "depense" and child["color"] == "#ff8800"  # hérités du parent
    assert c.post("/api/categories", json={"name": "projet test"}).status_code == 400  # doublon (casse ignorée)
    assert c.post("/api/categories", json={"name": "Trop profond", "parent_id": child["id"]}).status_code == 400
    assert c.post("/api/categories", json={"name": "Couleur", "color": "rouge"}).status_code == 422

    # Renommer + changer le type d'une catégorie principale : les sous-catégories suivent.
    r = c.patch(f"/api/categories/{p['id']}", json={"name": "Projet Testé", "kind": "revenu"})
    assert r.status_code == 200 and r.json()["name"] == "Projet Testé"
    assert _cats(c)[(p["id"], "Matériel")]["kind"] == "revenu"
    # Nouvelle couleur de la catégorie principale : la sous-catégorie qui avait la même la suit.
    c.patch(f"/api/categories/{p['id']}", json={"color": "#123456"})
    assert _cats(c)[(p["id"], "Matériel")]["color"] == "#123456"
    assert c.delete(f"/api/categories/{p['id']}").json()["deleted"] == 2


def test_delete_sends_operations_back_to_categorize(auth_client):
    c = auth_client
    acc = c.post("/api/accounts", json={"name": "Espèces", "type": "especes"}).json()
    cat = c.post("/api/categories", json={"name": "Éphémère"}).json()
    tx = _op(c, acc["id"], cat["id"])
    # Le vendeur est rangé dans cette catégorie (règle « vendeur → catégorie »).
    c.patch(f"/api/transactions/{tx['id']}", json={"category_id": cat["id"], "apply_to_merchant": True})
    usage = {u["id"]: u for u in c.get("/api/categories/usage").json()}
    assert usage[cat["id"]]["transactions"] == 1 and usage[cat["id"]]["rules"] == 1

    res = c.delete(f"/api/categories/{cat['id']}").json()
    assert res["transactions"] == 1 and res["rules"] == 1 and res["to_categorize"] == 1
    after = c.get("/api/transactions", params={"account_id": acc["id"]}).json()["items"][0]
    assert after["category_id"] is None and not after["category_locked"]
    groups = c.get("/api/transactions/to-categorize").json()
    assert any(g["merchant"] == "Vendeur Inventé Zeta" for g in groups)


def test_delete_with_move(auth_client):
    c = auth_client
    acc = c.post("/api/accounts", json={"name": "Espèces", "type": "especes"}).json()
    a = c.post("/api/categories", json={"name": "Ancienne"}).json()
    sub = c.post("/api/categories", json={"name": "Sous", "parent_id": a["id"]}).json()
    b = c.post("/api/categories", json={"name": "Nouvelle"}).json()
    _op(c, acc["id"], sub["id"])
    assert c.delete(f"/api/categories/{a['id']}", params={"move_to": sub["id"]}).status_code == 400  # destination supprimée aussi
    res = c.delete(f"/api/categories/{a['id']}", params={"move_to": b["id"]}).json()
    assert res["moved_to"] == b["id"] and res["to_categorize"] == 0
    tx = c.get("/api/transactions", params={"account_id": acc["id"]}).json()["items"][0]
    assert tx["category_id"] == b["id"]
    c.delete(f"/api/categories/{b['id']}")


def test_protected_categories(auth_client):
    c = auth_client
    cats = _cats(c)
    transfers = cats[(None, "Transferts")]
    internal = cats[(transfers["id"], "Virement interne")]
    assert internal["protected"] and transfers["protected"]
    assert c.delete(f"/api/categories/{transfers['id']}").status_code == 400
    assert c.delete(f"/api/categories/{internal['id']}").status_code == 400
    assert c.patch(f"/api/categories/{internal['id']}", json={"name": "Autre nom"}).status_code == 400
    assert c.patch(f"/api/categories/{internal['id']}", json={"icon": "🔁"}).status_code == 200


def test_renamed_default_category_is_not_recreated(auth_client):
    from app.db import get_sessionmaker
    from app.seed import ensure_categories, set_meta

    c = auth_client
    divers = _cats(c)[(None, "Divers")]
    assert c.patch(f"/api/categories/{divers['id']}", json={"name": "Divers renommé"}).status_code == 200
    with get_sessionmaker()() as db:
        set_meta(db, "categories_version", "0")  # simule une nouvelle version des catégories par défaut
        ensure_categories(db)
        db.commit()
    names = [x["name"] for x in c.get("/api/categories").json() if x["parent_id"] is None]
    assert "Divers" not in names and "Divers renommé" in names
    c.patch(f"/api/categories/{divers['id']}", json={"name": "Divers"})
