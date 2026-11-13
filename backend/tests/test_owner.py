"""Vendeurs similaires fusionnés + virements à ton nom (noms inventés)."""

from datetime import date

TODAY = date.today().isoformat()


def _op(c, account_id, merchant, amount=-1000):
    r = c.post("/api/transactions", json={"account_id": account_id, "booked_at": TODAY, "amount_cents": amount, "label": "Opération", "merchant": merchant})
    assert r.status_code == 201, r.text


def _merchants(c):
    return {m["name"]: m for m in c.get("/api/merchants").json()}


def test_similar_merchants_merged_or_suggested(auth_client):
    c = auth_client
    acc = c.post("/api/accounts", json={"name": "Courant", "type": "courant"}).json()
    for name in ("Monsieur Testeur Jea", "Monsieur Testeur Jea", "Monsieur Testeur Jean 12", "Monsieur Testeur Paul", "Boulangerie Inventée"):
        _op(c, acc["id"], name)

    # Troncature / référence : fusion automatique, en gardant le nom le plus utilisé.
    assert c.post("/api/merchants/auto-merge").json()["updated"] == 1
    names = _merchants(c)
    assert "Monsieur Testeur Jean 12" not in names and names["Monsieur Testeur Jea"]["count"] == 3

    # Même début mais suite différente : on demande.
    sugg = c.get("/api/merchants/similar").json()
    assert len(sugg) == 1 and {m["name"] for m in sugg[0]["merchants"]} == {"Monsieur Testeur Jea", "Monsieur Testeur Paul"}
    ids = [m["id"] for m in sugg[0]["merchants"]]
    assert c.post("/api/merchants/similar/ignore", json={"ids": ids}).status_code == 200
    assert c.get("/api/merchants/similar").json() == []

    # Fusion manuelle d'un groupe, avec un nouveau nom.
    keep = names["Monsieur Testeur Jea"]["id"]
    r = c.post("/api/merchants/merge-group", json={"ids": ids, "target_id": keep, "name": "Virements Testeur"})
    assert r.status_code == 200 and _merchants(c)["Virements Testeur"]["count"] == 4


def test_import_reuses_similar_merchant_and_owner_names(auth_client):
    from app.connectors.enable_banking import to_statement
    from app.db import get_sessionmaker
    from app.services.importing import ingest

    c = auth_client
    acc = c.post("/api/accounts", json={"name": "Courant", "type": "courant"}).json()
    _op(c, acc["id"], "Monsieur Testeur Jea")
    synced = [{"entry_reference": "R1", "status": "BOOK", "credit_debit_indicator": "DBIT", "booking_date": TODAY,
               "transaction_amount": {"amount": "50.00", "currency": "EUR"}, "creditor": {"name": "MONSIEUR TESTEUR JEAN 7"}}]
    with get_sessionmaker()() as db:
        ingest(db, to_statement(synced, [], "Courant"), acc["id"], None, "Banque")
        db.commit()
    items = c.get("/api/transactions", params={"account_id": acc["id"]}).json()["items"]
    assert {t["merchant"] for t in items} == {"Monsieur Testeur Jea"}

    # Ton nom de titulaire : ces opérations deviennent des virements internes (hors statistiques).
    preview = c.post("/api/settings/owner/preview", json={"signatures": ["monsieur testeur"]}).json()
    assert preview["matching_merchants"] == ["Monsieur Testeur Jea"] and preview["operations"] == 2
    assert c.get("/api/settings/owner").json()["signatures"] == []  # l'aperçu n'enregistre rien
    state = c.put("/api/settings/owner", json={"signatures": ["Monsieur Testeur", "x"]}).json()
    assert state["signatures"] == ["MONSIEUR TESTEUR"]
    items = c.get("/api/transactions", params={"account_id": acc["id"]}).json()["items"]
    assert all(t["is_transfer"] for t in items)
