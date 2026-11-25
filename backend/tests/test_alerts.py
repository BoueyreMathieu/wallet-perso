"""Alertes et réglages des notifications (données inventées)."""

from datetime import date


def test_budget_alert_and_kind_toggle(auth_client):
    c = auth_client
    acc = c.post("/api/accounts", json={"name": "Courant inventé", "type": "courant", "initial_balance_cents": 100000}).json()
    cats = {x["name"]: x for x in c.get("/api/categories").json()}
    bars = cats["Bars"]["id"]
    c.post("/api/transactions", json={"account_id": acc["id"], "booked_at": date.today().isoformat(), "amount_cents": -6000,
                                      "label": "CB BAR INVENTE", "merchant": "Bar inventé", "category_id": bars})
    c.put(f"/api/budgets/{bars}", json={"monthly_amount_cents": 5000})

    alerts = c.get("/api/alerts").json()["alerts"]
    budget = next(a for a in alerts if a["kind"] == "budgets")
    assert budget["level"] == "danger" and budget["key"] == f"budget:{bars}:{date.today():%Y-%m}:depasse"
    assert budget["deep"] == "budgets" and "dépassé" in budget["title"]

    s = c.get("/api/settings/notifications").json()
    assert {k["id"] for k in s["kinds"]} == {"budgets", "tresorerie", "banque", "revenus", "contrats", "autres"} and all(k["enabled"] for k in s["kinds"])
    s = c.put("/api/settings/notifications", json={"kinds": {"budgets": False, "inconnu": True}}).json()
    assert next(k for k in s["kinds"] if k["id"] == "budgets")["enabled"] is False
    assert not any(a["kind"] == "budgets" for a in c.get("/api/alerts").json()["alerts"])


def test_accounts_show_connection_and_balance_check(auth_client):
    acc = auth_client.post("/api/accounts", json={"name": "Manuel inventé", "type": "courant"}).json()
    row = next(a for a in auth_client.get("/api/accounts").json() if a["id"] == acc["id"])
    assert row["connection_id"] is None and row["balance_gap_cents"] is None  # pas synchronisé : rien à contrôler
    assert auth_client.post(f"/api/accounts/{acc['id']}/balance-check/ok").json() == {"ok": True}
    assert auth_client.post("/api/accounts/999999/balance-check/ok").status_code == 404
