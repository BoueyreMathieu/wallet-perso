"""Découper une opération, dépenses partagées (avances), budget global, jour de paie, accueil (données inventées)."""

from datetime import date, timedelta


def _setup(c):
    acc = c.post("/api/accounts", json={"name": "Courant inventé", "type": "courant", "initial_balance_cents": 100000}).json()
    cats = {x["name"]: x["id"] for x in c.get("/api/categories").json()}
    return acc, cats


def test_split_and_advance(auth_client):
    c = auth_client
    acc, cats = _setup(c)
    day = date.today()  # saisie après le solde connu : elle compte dans le solde
    t = c.post("/api/transactions", json={"account_id": acc["id"], "booked_at": day.isoformat(), "amount_cents": -9000,
                                          "label": "CB RESTAURANT INVENTE", "category_id": cats["Restaurants"]}).json()
    bal = lambda: next(a for a in c.get("/api/accounts").json() if a["id"] == acc["id"])["balance_cents"]  # noqa: E731
    assert bal() == 91000
    bad = c.post(f"/api/transactions/{t['id']}/split", json={"parts": [{"amount_cents": -5000}, {"amount_cents": -3000}]})
    assert bad.status_code == 422  # la somme ne fait pas 90 €
    r = c.post(f"/api/transactions/{t['id']}/split", json={"parts": [
        {"amount_cents": -3000, "category_id": cats["Restaurants"]},
        {"amount_cents": -6000, "category_id": cats["Restaurants"], "person": "Ami inventé"},
    ]}).json()
    assert r["split"] and len(r["parts"]) == 2 and r["parts"][1]["person"] == "Ami inventé"
    assert bal() == 91000  # le solde ne change pas
    items = {x["id"]: x for x in c.get("/api/transactions", params={"account_id": acc["id"]}).json()["items"]}
    assert not items[t["id"]]["counted"] and items[t["id"]]["details"]["decoupee"]
    # Seule ma part compte comme dépense.
    month = c.get("/api/dashboard", params={"month": day.strftime("%Y-%m")}).json()
    assert month["spent_cents"] == 3000

    # On me doit 60 € ; le remboursement reçu ne compte pas comme un revenu.
    [adv] = c.get("/api/advances").json()
    assert adv["person"] == "Ami inventé" and adv["amount_cents"] == 6000 and not adv["settled"]
    refund = c.post("/api/transactions", json={"account_id": acc["id"], "booked_at": day.isoformat(), "amount_cents": 6000,
                                               "label": "VIR AMI INVENTE"}).json()
    assert c.post(f"/api/advances/{adv['id']}/settle", json={"transaction_id": refund["id"]}).json() == {"ok": True}
    assert c.get("/api/advances").json()[0]["settled"]
    month = c.get("/api/dashboard", params={"month": day.strftime("%Y-%m")}).json()
    assert month["income_cents"] == 0 and month["spent_cents"] == 3000
    # Annuler le découpage : l'opération compte de nouveau en entier, le remboursement redevient un revenu.
    c.delete(f"/api/transactions/{t['id']}/split")
    month = c.get("/api/dashboard", params={"month": day.strftime("%Y-%m")}).json()
    assert month["spent_cents"] == 9000 and month["income_cents"] == 6000 and c.get("/api/advances").json() == []


def test_global_budget_payday_and_home_layout(auth_client):
    c = auth_client
    acc, cats = _setup(c)
    c.post("/api/transactions", json={"account_id": acc["id"], "booked_at": date.today().isoformat(), "amount_cents": -4000,
                                      "label": "CB SUPERMARCHE INVENTE", "category_id": cats["Courses"]})
    assert c.get("/api/budgets").json()["global"] is None
    assert c.put("/api/budgets/global", json={"monthly_amount_cents": 150000}).status_code == 200
    g = c.get("/api/budgets").json()["global"]
    assert g["budget_cents"] == 150000 and g["spent_cents"] == 4000 and g["level"] == "ok"
    c.put("/api/budgets/global", json={"monthly_amount_cents": None})
    assert c.get("/api/budgets").json()["global"] is None

    # Jour de paie réglé à la main : le salaire est attendu ce jour-là.
    nxt = date.today() + timedelta(days=40)
    c.post("/api/recurring", json={"label": "Salaire inventé", "account_id": acc["id"], "amount_cents": 200000, "frequency": "mensuel",
                                   "next_date": nxt.isoformat()})
    assert c.put("/api/settings/payday", json={"day": 5}).json() == {"day": 5}
    f = c.get("/api/forecast", params={"horizon": 90}).json()
    assert all(date.fromisoformat(e["date"]).day == 5 for e in f["events"] if e["label"] == "Salaire inventé")
    c.put("/api/settings/payday", json={"day": None})
    assert c.get("/api/settings/payday").json() == {"day": None}

    # Accueil : une disposition pour l'ordinateur, une autre pour le téléphone.
    assert c.get("/api/settings/home-layout", params={"platform": "web"}).json()["cards"] is None
    c.put("/api/settings/home-layout", params={"platform": "mobile"}, json={"cards": [{"id": "kpis"}, {"id": "accounts", "hidden": True}]})
    assert c.get("/api/settings/home-layout", params={"platform": "mobile"}).json()["cards"][1] == {"id": "accounts", "hidden": True}
    assert c.get("/api/settings/home-layout", params={"platform": "web"}).json()["cards"] is None
    assert c.get("/api/settings/home-layout", params={"platform": "tv"}).status_code == 422
