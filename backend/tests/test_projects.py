"""Projets par étiquette, contrats, comparaison annuelle et patrimoine (données inventées)."""

from datetime import date, timedelta

from app.recurrence import add_months


def _op(c, acc, day, amount, label, category=None, tags=None):
    r = c.post("/api/transactions", json={"account_id": acc["id"], "booked_at": day.isoformat(), "amount_cents": amount, "label": label,
                                          "category_id": category, "tag_ids": tags or []})
    assert r.status_code == 201, r.text
    return r.json()


def test_project_by_tag_with_budget_and_dates(auth_client):
    c = auth_client
    acc = c.post("/api/accounts", json={"name": "Courant inventé", "type": "courant", "initial_balance_cents": 500000}).json()
    cats = {x["name"]: x for x in c.get("/api/categories").json()}
    p = c.post("/api/projects", json={"name": "Voyage inventé", "budget_cents": 50000, "start_date": (date.today() - timedelta(days=30)).isoformat()}).json()
    assert p["name"] == "Voyage inventé" and p["net_cents"] == 0 and p["level"] == "ok"
    tag = p["tag_id"]
    _op(c, acc, date.today(), -30000, "HOTEL INVENTE", cats["Restaurants"]["id"], [tag])
    _op(c, acc, date.today(), -15000, "TRAIN INVENTE", cats["Restaurants"]["id"], [tag])
    _op(c, acc, date.today(), 5000, "REMBOURSEMENT INVENTE", cats["Restaurants"]["id"], [tag])
    _op(c, acc, date.today() - timedelta(days=60), -99900, "AVANT LE PROJET", cats["Restaurants"]["id"], [tag])  # hors dates
    _op(c, acc, date.today(), -7000, "SANS ETIQUETTE")
    p = next(x for x in c.get("/api/projects").json() if x["id"] == p["id"])
    assert p["spent_cents"] == 45000 and p["refunds_cents"] == 5000 and p["net_cents"] == 40000 and p["count"] == 3
    assert p["remaining_cents"] == 10000 and p["level"] == "alerte"
    assert (cats["Restaurants"]["parent_id"] or cats["Restaurants"]["id"]) in {x["category_id"] for x in p["by_category"]}
    assert any(a["key"] == f"projet:{p['id']}:alerte" for a in c.get("/api/alerts").json()["alerts"])

    assert c.post("/api/projects", json={"tag_id": tag}).status_code == 409  # déjà suivie
    assert c.post("/api/projects", json={}).status_code == 422
    p = c.patch(f"/api/projects/{p['id']}", json={"budget_cents": 0, "clear_dates": True}).json()
    assert p["budget_cents"] is None and p["count"] == 4 and p["net_cents"] == 40000 + 99900  # sans dates : tout compte
    assert c.patch(f"/api/projects/{p['id']}", json={"archived": True}).json()["archived"] is True
    assert c.get("/api/projects").json() == [] and len(c.get("/api/projects", params={"archived": True}).json()) == 1
    assert c.delete(f"/api/projects/{p['id']}").json() == {"ok": True}
    assert any(t["id"] == tag for t in c.get("/api/tags").json())  # l'étiquette reste


def test_contracts_deadline_and_tacit_renewal(auth_client):
    c = auth_client
    acc = c.post("/api/accounts", json={"name": "Courant inventé", "type": "courant"}).json()
    s = c.post("/api/recurring", json={"label": "Assurance inventée", "account_id": acc["id"], "amount_cents": -2500, "frequency": "mensuel",
                                       "next_date": date.today().isoformat()}).json()
    renewal = date.today() + timedelta(days=40)
    k = c.post("/api/contracts", json={"recurring_id": s["id"], "renewal_date": renewal.isoformat(), "notice_days": 30}).json()
    assert k["label"] == "Assurance inventée" and k["amount_cents"] == -2500 and k["amount_from_recurring"]
    assert k["deadline"] == (renewal - timedelta(days=30)).isoformat() and k["days_to_deadline"] == 10 and k["state"] == "bientot"
    assert any(a["key"].startswith(f"contrat:{k['id']}:") for a in c.get("/api/alerts").json()["alerts"])
    # Échéance passée avec reconduction tacite : elle avance d'un an.
    past = date.today() - timedelta(days=5)
    k2 = c.post("/api/contracts", json={"label": "Box inventée", "renewal_date": past.isoformat(), "renew_months": 12}).json()
    listed = {x["id"]: x for x in c.get("/api/contracts").json()}
    assert listed[k2["id"]]["renewal_date"] == add_months(past, 12).isoformat()
    k3 = c.patch(f"/api/contracts/{k2['id']}", json={"renew_months": 0, "renewal_date": past.isoformat()}).json()
    assert k3["renew_months"] is None and k3["state"] == "termine"
    assert c.post("/api/contracts", json={"renewal_date": renewal.isoformat()}).status_code == 422  # sans nom ni récurrent
    assert c.delete(f"/api/contracts/{k['id']}").json() == {"ok": True}


def test_compare_years(auth_client):
    c = auth_client
    acc = c.post("/api/accounts", json={"name": "Courant inventé", "type": "courant"}).json()
    cats = {x["name"]: x for x in c.get("/api/categories").json()}
    today = date.today()
    _op(c, acc, today, -12000, "COURSES INVENTEES", cats["Courses"]["id"])
    _op(c, acc, add_months(today, -12), -8000, "COURSES AN DERNIER", cats["Courses"]["id"])
    _op(c, acc, today, 200000, "SALAIRE INVENTE", cats["Salaire"]["id"])
    for mode in ("ytd", "rolling"):
        r = c.get("/api/compare", params={"mode": mode}).json()
        assert r["spent_cents"] == 12000 and r["prev_spent_cents"] == 8000 and r["income_cents"] == 200000
        courses = next(x for x in r["categories"] if x["category_id"] == cats["Courses"]["id"])
        assert courses["diff_cents"] == 4000 and courses["diff_pct"] == 0.5 and courses["parent_id"] == cats["Courses"]["parent_id"]
        assert r["months"][-1]["cur_cents"] == 12000 and r["months"][-1]["prev_cents"] == 8000
    assert len(c.get("/api/compare", params={"mode": "rolling"}).json()["months"]) == 12
    assert c.get("/api/compare", params={"mode": "autre"}).status_code == 422


def test_patrimoine_with_car_loan_and_savings(auth_client):
    c = auth_client
    car = c.post("/api/accounts", json={"name": "Voiture inventée", "type": "bien"}).json()
    loan = c.post("/api/accounts", json={"name": "Crédit auto inventé", "type": "credit"}).json()
    livret = c.post("/api/accounts", json={"name": "Livret inventé", "type": "epargne", "initial_balance_cents": 2500000}).json()
    year_ago = date.today() - timedelta(days=365)
    c.put(f"/api/accounts/{car['id']}/params", json={"purchase_cents": 2000000, "purchase_date": year_ago.isoformat(), "depreciation_pct": 15})
    c.put(f"/api/accounts/{loan['id']}/params", json={"principal_cents": 1200000, "rate_pct": 0, "months": 12,
                                                     "first_payment": (date.today() - timedelta(days=1)).isoformat()})
    assert c.put(f"/api/accounts/{livret['id']}/params", json={"rate_pct": 2.4, "ceiling_cents": 2295000}).json()["params"] == {
        "rate_pct": 2.4, "ceiling_cents": 2295000}
    p = c.get("/api/patrimoine").json()
    rows = {r["id"]: r for r in p["accounts"]}
    assert 1690000 <= rows[car["id"]]["balance_cents"] <= 1710000  # environ −15 % en un an
    assert rows[loan["id"]]["balance_cents"] == -1100000 and rows[loan["id"]]["details"]["payments_left"] == 11
    assert rows[livret["id"]]["details"]["at_ceiling"] and rows[livret["id"]]["details"]["yearly_interest_cents"] == round(2295000 * 0.024)
    assert p["debts_cents"] == 1100000 and p["net_worth_cents"] == p["assets_cents"] - 1100000 and len(p["history"]) == 24
    # La valeur calculée sert de solde partout (page Comptes, patrimoine de l'accueil).
    assert next(a for a in c.get("/api/accounts").json() if a["id"] == car["id"])["balance_cents"] == rows[car["id"]]["balance_cents"]
    assert any(a["key"].startswith(f"plafond:{livret['id']}:") for a in c.get("/api/alerts").json()["alerts"])
    courant = c.post("/api/accounts", json={"name": "Courant inventé", "type": "courant"}).json()
    assert c.put(f"/api/accounts/{courant['id']}/params", json={"rate_pct": 1}).status_code == 422


def test_parent_budget_shows_each_subcategory(auth_client):
    c = auth_client
    acc = c.post("/api/accounts", json={"name": "Courant inventé", "type": "courant"}).json()
    cats = {x["name"]: x for x in c.get("/api/categories").json()}
    parent = cats["Courses"]["parent_id"]
    sibling = next(x for x in cats.values() if x["parent_id"] == parent and x["id"] != cats["Courses"]["id"])
    _op(c, acc, date.today(), -3000, "COURSES INVENTEES", cats["Courses"]["id"])
    _op(c, acc, date.today(), -1000, "AUTRE INVENTE", sibling["id"])
    c.put(f"/api/budgets/{parent}", json={"monthly_amount_cents": 50000})
    c.put(f"/api/budgets/{sibling['id']}", json={"monthly_amount_cents": 2000})  # budget à part sur une sous-catégorie
    b = c.get("/api/budgets").json()
    top = next(i for i in b["items"] if i["category_id"] == parent)
    assert top["spent_cents"] == 4000 and top["children"] == [
        {"category_id": cats["Courses"]["id"], "spent_cents": 3000}, {"category_id": sibling["id"], "spent_cents": 1000}]
    assert next(i for i in b["items"] if i["category_id"] == sibling["id"])["children"] == []
    assert b["total_budget_cents"] == 50000 and b["total_spent_cents"] == 4000  # la sous-catégorie n'est pas comptée deux fois
