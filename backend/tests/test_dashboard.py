"""Tableau de bord (données inventées)."""

from datetime import date, timedelta


def test_dashboard_month_summary(auth_client):
    c = auth_client
    today = date.today()
    first = today.replace(day=1)
    prev_day = first - timedelta(days=1)
    acc = c.post("/api/accounts", json={"name": "Espèces", "type": "especes", "initial_balance_cents": 0}).json()
    sav = c.post("/api/accounts", json={"name": "Livret", "type": "epargne"}).json()
    cats = {x["name"]: x for x in c.get("/api/categories").json()}

    def op(day, amount, label, account=acc, category=None):
        r = c.post("/api/transactions", json={"account_id": account["id"], "booked_at": day.isoformat(), "amount_cents": amount, "label": label, "category_id": category})
        assert r.status_code == 201, r.text
        return r.json()

    op(first, -3000, "Supermarché inventé", category=cats["Courses"]["id"])
    op(first, -1000, "Pizzeria inventée", category=cats["Restaurants"]["id"])
    op(first, 200000, "Salaire inventé", category=cats["Salaire"]["id"])
    op(prev_day, -5000, "Supermarché inventé", category=cats["Courses"]["id"])
    # Virement entre mes comptes : hors statistiques.
    op(first, -50000, "VIREMENT VERS LIVRET")
    op(first, 50000, "VIREMENT RECU", account=sav)
    c.post("/api/transfers/detect")

    d = c.get("/api/dashboard").json()
    assert d["spent_cents"] == 4000 and d["income_cents"] == 200000
    assert d["prev_spent_cents"] == 5000
    assert d["prev_income_same_day_cents"] == 0
    food = next(x for x in d["by_category"] if x["category_id"] == cats["Alimentation"]["id"])
    assert food["spent_cents"] == 4000 and food["prev_spent_cents"] == 5000 and food["count"] == 2
    assert d["top_expenses"][0]["amount_cents"] == -3000
    assert len(d["months"]) == 12 and d["months"][-1]["spent_cents"] == 4000
    assert d["daily_cumulative"][-1] == 4000
    assert c.get("/api/dashboard", params={"month": "2026-13"}).status_code == 422

    # Épargne : le virement vers le livret compte comme épargne versée.
    assert d["saved_cents"] == 50000 and d["savings_rate"] == 0.25
    assert d["months"][-1]["saved_cents"] == 50000
    only_livret = c.get("/api/dashboard", params={"accounts": str(sav["id"])}).json()
    assert only_livret["saved_cents"] == 50000  # vu du livret seul : l'autre côté n'est pas sélectionné
    both = c.get("/api/dashboard", params={"accounts": f"{acc['id']},{sav['id']}"}).json()
    assert both["saved_cents"] == 50000  # pas compté deux fois

    # Période libre : la période précédente a la même durée.
    p = c.get("/api/dashboard", params={"date_from": prev_day.isoformat(), "date_to": today.isoformat()}).json()
    assert p["period"] == "period" and p["spent_cents"] == 9000
    assert c.get("/api/dashboard", params={"date_from": today.isoformat(), "date_to": prev_day.isoformat()}).status_code == 422


def test_dashboard_filters_by_account_and_category(auth_client):
    c = auth_client
    first = date.today().replace(day=1)
    a = c.post("/api/accounts", json={"name": "Compte A", "type": "courant"}).json()
    b = c.post("/api/accounts", json={"name": "Compte B", "type": "courant"}).json()
    cats = {x["name"]: x for x in c.get("/api/categories").json()}

    def op(account, amount, cat):
        c.post("/api/transactions", json={"account_id": account["id"], "booked_at": first.isoformat(), "amount_cents": amount, "label": "Achat inventé", "category_id": cats[cat]["id"]})

    op(a, -3000, "Courses")
    op(a, -1000, "Restaurants")
    op(b, -7000, "Courses")
    op(b, -2000, "Carburant")

    assert c.get("/api/dashboard").json()["spent_cents"] == 13000
    only_a = c.get("/api/dashboard", params={"accounts": str(a["id"])}).json()
    assert only_a["spent_cents"] == 4000
    both = c.get("/api/dashboard", params={"accounts": f"{a['id']},{b['id']}"}).json()
    assert both["spent_cents"] == 13000

    food = cats["Alimentation"]["id"]
    focus = c.get("/api/dashboard", params={"category_id": food}).json()
    assert focus["focus_category_id"] == food and focus["spent_cents"] == 11000
    subs = {x["category_id"]: x["spent_cents"] for x in focus["by_category"]}
    assert subs == {cats["Courses"]["id"]: 10000, cats["Restaurants"]["id"]: 1000}
    assert len(focus["transactions"]) == 3
    focus_a = c.get("/api/dashboard", params={"category_id": food, "accounts": str(a["id"])}).json()
    assert focus_a["spent_cents"] == 4000
    assert c.get("/api/dashboard", params={"category_id": 999999}).status_code == 404


def test_months_history_for_scrolling_chart(auth_client):
    c = auth_client
    acc = c.post("/api/accounts", json={"name": "Espèces", "type": "especes"}).json()
    old = date.today().replace(day=1) - timedelta(days=500)
    c.post("/api/transactions", json={"account_id": acc["id"], "booked_at": old.isoformat(), "amount_cents": -1234, "label": "Achat ancien"})
    c.post("/api/transactions", json={"account_id": acc["id"], "booked_at": date.today().isoformat(), "amount_cents": -100, "label": "Achat récent"})
    months = c.get("/api/dashboard/months").json()
    assert len(months) >= 17  # depuis la plus ancienne opération
    assert months[-1]["month"] == date.today().strftime("%Y-%m")
    assert next(m for m in months if m["month"] == old.strftime("%Y-%m"))["spent_cents"] == 1234
    assert months[-1]["net_worth_cents"] == -1334 and months[-1]["spent_cents"] == 100
