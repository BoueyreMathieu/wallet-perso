"""Récurrents, budgets et prévision de trésorerie (données inventées)."""

from datetime import date, timedelta

from app.recurrence import add_months


def _setup(c):
    acc = c.post("/api/accounts", json={"name": "Courant inventé", "type": "courant", "initial_balance_cents": 100000}).json()
    cats = {x["name"]: x for x in c.get("/api/categories").json()}

    def op(day, amount, label, merchant=None, category=None, account=acc):
        r = c.post("/api/transactions", json={
            "account_id": account["id"], "booked_at": day.isoformat(), "amount_cents": amount, "label": label,
            "merchant": merchant, "category_id": category,
        })
        assert r.status_code == 201, r.text
        return r.json()

    return acc, cats, op


def _monthly_dates(n: int) -> list[date]:
    """n échéances mensuelles, la plus récente il y a 3 jours."""
    base = date.today() - timedelta(days=3)
    return [add_months(base, -i) for i in range(n)][::-1]


def test_recurring_detection_confirm_and_ignore(auth_client):
    c = auth_client
    acc, cats, op = _setup(c)
    ids = [op(d, -999, "PRLV MUSIQUE INVENTEE", merchant="Musique inventée", category=cats["Abonnements"]["id"])["id"] for d in _monthly_dates(6)]
    for d in _monthly_dates(5):
        op(d, 210000, "SALAIRE INVENTE", merchant="Employeur inventé", category=cats["Salaire"]["id"])
    for i, d in enumerate(_monthly_dates(4)):
        op(d - timedelta(days=i * 3 + 1), -(2000 + i * 1733), "CB MAGASIN INVENTE", merchant="Magasin inventé", category=cats["Courses"]["id"])

    assert c.post("/api/recurring/refresh").json()["created"] == 2
    data = c.get("/api/recurring").json()
    by_label = {i["label"]: i for i in data["items"]}
    music, salary = by_label["Musique inventée"], by_label["Employeur inventé"]
    assert "Magasin inventé" not in by_label
    assert music["status"] == "suggere" and music["frequency"] == "mensuel" and music["kind"] == "depense"
    assert music["occurrences"] == 6 and music["total_cents"] == -999 * 6 and music["next_date"] > date.today().isoformat()
    assert salary["kind"] == "revenu" and salary["amount_cents"] == 210000
    assert data["to_confirm"] == 2 and data["monthly_out_cents"] == 999 and data["monthly_in_cents"] == 210000
    assert len(c.get(f"/api/recurring/{music['id']}/transactions").json()) == 6
    assert c.get("/api/transactions", params={"q": "MUSIQUE"}).json()["items"][0]["recurring_id"] == music["id"]

    # Confirmer l'abonnement, refuser le salaire : une nouvelle détection ne le repropose pas.
    assert c.patch(f"/api/recurring/{music['id']}", json={"status": "actif", "label": "Musique"}).json()["status"] == "actif"
    c.delete(f"/api/recurring/{salary['id']}")
    c.post("/api/recurring/refresh")
    data = c.get("/api/recurring").json()
    assert [(i["label"], i["status"]) for i in data["items"]] == [("Musique", "actif")]
    assert data["to_confirm"] == 0
    statuses = {i["label"]: i["status"] for i in c.get("/api/recurring", params={"all": True}).json()["items"]}
    assert statuses["Employeur inventé"] == "ignore"
    assert all(i["id"] in ids for i in c.get(f"/api/recurring/{music['id']}/transactions").json())


def test_price_increase_reported_on_home(auth_client):
    c = auth_client
    acc, cats, op = _setup(c)
    dates = _monthly_dates(6)
    for d in dates[:4]:
        op(d, -999, "PRLV VIDEO INVENTEE", merchant="Vidéo inventée", category=cats["Abonnements"]["id"])
    for d in dates[4:]:
        op(d, -1299, "PRLV VIDEO INVENTEE", merchant="Vidéo inventée", category=cats["Abonnements"]["id"])
    c.post("/api/recurring/refresh")
    [s] = c.get("/api/recurring").json()["items"]
    assert s["price_increase"] and s["previous_amount_cents"] == -999 and s["amount_cents"] == -1299
    todo = c.get("/api/dashboard").json()["todo"]
    assert todo["price_increases"] == ["Vidéo inventée"] and todo["recurring_to_confirm"] == 1


def test_manual_and_from_transaction(auth_client):
    c = auth_client
    acc, cats, op = _setup(c)
    soon = date.today() + timedelta(days=10)
    r = c.post("/api/recurring", json={"label": "Assurance inventée", "account_id": acc["id"], "amount_cents": -30000, "frequency": "annuel", "next_date": soon.isoformat()})
    assert r.status_code == 201 and r.json()["status"] == "actif" and r.json()["monthly_cents"] == -2500
    t = op(date.today() - timedelta(days=2), -1500, "PRLV SALLE DE SPORT", merchant="Sport inventé", category=cats["Abonnements"]["id"])
    s = c.post(f"/api/recurring/from-transaction/{t['id']}", json={"frequency": "mensuel"}).json()
    assert s["source"] == "manuel" and s["occurrences"] == 1 and s["next_date"] == add_months(date.today() - timedelta(days=2), 1).isoformat()
    f = c.get("/api/forecast", params={"horizon": 60}).json()
    labels = [e["label"] for e in f["events"]]
    assert "Assurance inventée" in labels and "Sport inventé" in labels
    # Une série déclarée à la main se supprime vraiment.
    c.delete(f"/api/recurring/{r.json()['id']}")
    assert "Assurance inventée" not in [i["label"] for i in c.get("/api/recurring", params={"all": True}).json()["items"]]


def test_budgets(auth_client):
    c = auth_client
    acc, cats, op = _setup(c)
    resto, salary = cats["Restaurants"]["id"], cats["Salaire"]["id"]
    assert c.put(f"/api/budgets/{salary}", json={"monthly_amount_cents": 1000}).status_code == 422
    assert c.put(f"/api/budgets/{resto}", json={"monthly_amount_cents": 10000}).status_code == 200
    op(date.today(), -8500, "RESTAURANT INVENTE", category=resto)
    b = c.get("/api/budgets").json()
    [item] = b["items"]
    assert item["spent_cents"] == 8500 and item["level"] == "alerte" and item["remaining_cents"] == 1500
    op(date.today(), -2000, "RESTAURANT INVENTE", category=resto)
    assert c.get("/api/budgets").json()["items"][0]["level"] == "depasse"
    assert c.get("/api/dashboard").json()["todo"]["budget_alerts"] == [{"category_id": resto, "level": "depasse"}]
    # Suggestions : catégories principales dépensées les 3 derniers mois, sans budget.
    first = date.today().replace(day=1)
    for i in (1, 2, 3):
        op(add_months(first, -i) + timedelta(days=4), -24000, "SUPERMARCHE INVENTE", category=cats["Courses"]["id"])
    sugg = c.get("/api/budgets").json()["suggestions"]
    food = next(s for s in sugg if s["category_id"] == cats["Alimentation"]["id"])
    assert food["average_cents"] == 24000 and food["suggested_cents"] == 25000
    c.delete(f"/api/budgets/{resto}")
    assert c.get("/api/budgets").json()["items"] == []
    assert c.get("/api/budgets", params={"month": "2026-13"}).status_code == 422


def test_forecast(auth_client):
    c = auth_client
    acc, cats, op = _setup(c)
    for d in _monthly_dates(4):
        op(d, -5000, "PRLV ENERGIE INVENTEE", merchant="Énergie inventée", category=cats["Abonnements"]["id"])
    c.post("/api/recurring/refresh")
    f = c.get("/api/forecast", params={"horizon": 45}).json()
    assert f["accounts"] == ["Courant inventé"] and f["start_balance_cents"] == 100000
    energy = [e for e in f["events"] if e["label"] == "Énergie inventée"]
    assert len(energy) >= 1 and energy[0]["amount_cents"] == -5000 and energy[0]["kind"] == "depense"
    days = (date.fromisoformat(f["horizon"]) - date.today()).days
    assert len(f["points"]) == days + 1
    t = f["totals"]
    assert t["fixe_cents"] == 5000 * len(energy)
    last = f["points"][-1]
    assert last["balance_cents"] == f["end_balance_cents"]
    assert abs(f["end_balance_cents"] - (100000 + t["income_cents"] - t["fixe_cents"] - t["essentiel_cents"] - t["plaisir_cents"] - t["epargne_cents"])) <= 3
    assert last["socle_cents"] >= last["after_essentials_cents"] >= last["balance_cents"]
    assert f["lowest"]["balance_cents"] <= f["start_balance_cents"]
    # Périodes : fin du mois prochain, date choisie, erreurs.
    nxt = c.get("/api/forecast", params={"horizon": "fin_mois_prochain"}).json()["horizon"]
    assert date.fromisoformat(nxt).day >= 28
    chosen = (date.today() + timedelta(days=200)).isoformat()
    assert c.get("/api/forecast", params={"end_date": chosen}).json()["horizon"] == chosen
    assert c.get("/api/forecast", params={"end_date": date.today().isoformat()}).status_code == 422
    assert c.get("/api/forecast", params={"horizon": "bientot"}).status_code == 422


def test_layers_projection_scenario_and_category_nature(auth_client):
    from app.trends import weighted_level

    c = auth_client
    acc, cats, op = _setup(c)
    for i, d in enumerate(_monthly_dates(4)):
        # Salaire dont le libellé (et donc le vendeur) change chaque mois : repéré par sa catégorie.
        op(d, 210000, f"VIR SALAIRE MOIS {i}", merchant=f"Employeur inventé {i}", category=cats["Salaire"]["id"])
        op(d, -80000, "PRLV LOYER INVENTE", merchant="Propriétaire inventé", category=cats["Loyer / crédit"]["id"])
    first = date.today().replace(day=1)
    # Dates irrégulières : des habitudes, pas des récurrents.
    for i, (day, bar, shop_day) in enumerate([(3, 5000, 5), (18, 7000, 20), (9, 6000, 8)]):
        month = add_months(first, i - 3)
        op(month + timedelta(days=shop_day - 1), -(12000 + 700 * i), "CB SUPERMARCHE", merchant="Supermarché inventé", category=cats["Courses"]["id"])
        op(month + timedelta(days=19), -18000, "CB MARCHE", merchant=f"Marché inventé {i}", category=cats["Courses"]["id"])
        op(month + timedelta(days=day - 1), -bar, "CB BAR INVENTE", merchant="Bar inventé", category=cats["Bars"]["id"])
    c.post("/api/recurring/refresh")

    rec = {i["label"]: i for i in c.get("/api/recurring").json()["items"]}
    assert rec["Salaire"]["basis"] == "categorie" and rec["Salaire"]["amount_cents"] == 210000
    assert rec["Propriétaire inventé"]["basis"] == "vendeur"

    natures = {x["name"]: x["nature_effective"] for x in c.get("/api/categories").json()}
    assert natures["Courses"] == "essentiel" and natures["Bars"] == "plaisir" and natures["Loyer / crédit"] == "fixe"
    assert natures["Salaire"] is None

    courses = weighted_level([30000, 30700, 31400])
    bars = weighted_level([5000, 7000, 6000])
    p = c.get("/api/projection", params={"months": 6}).json()
    layers = p["model"]["layers"]
    assert layers["essentiel"]["trend_cents"] == courses and layers["plaisir"]["trend_cents"] == bars and layers["fixe"]["trend_cents"] == 0
    food = next(g for g in p["model"]["groups"] if g["category_id"] == cats["Alimentation"]["id"])
    assert {ch["category_id"] for ch in food["children"]} == {cats["Courses"]["id"]}
    assert len(p["months"]) == 6 and p["months"][0]["partial"]
    m1 = p["months"][1]
    assert m1["income_cents"] == 210000 and m1["fixe_cents"] == 80000
    assert abs(m1["essentiel_cents"] - courses) <= 1 and abs(m1["plaisir_cents"] - bars) <= 1 and m1["epargne_cents"] == 0
    assert abs(m1["net_cents"] - (210000 - 80000 - courses - bars)) <= 2
    assert p["end_balance_cents"] == p["months"][-1]["end_balance_cents"]

    # Scénario : plaisirs à 50 %, épargne en plus, budgets appliqués, objectif sur une catégorie.
    c.put(f"/api/budgets/{cats['Courses']['id']}", json={"monthly_amount_cents": 20000})
    s = c.post("/api/projection", params={"months": 6}, json={"plaisir_pct": 50, "extra_saving_cents": 10000, "apply_budgets": True}).json()
    s1 = s["months"][1]
    assert abs(s1["plaisir_cents"] - bars / 2) <= 1 and s1["epargne_cents"] == 10000 and abs(s1["essentiel_cents"] - 20000) <= 1
    assert s["end_balance_cents"] > s["baseline_end_cents"] - 6 * 10000
    t = c.post("/api/projection", params={"months": 3}, json={"targets": {str(cats["Bars"]["id"]): 2000}}).json()
    assert abs(t["months"][1]["plaisir_cents"] - 2000) <= 1 and t["scenario"]["active"]
    f = c.post("/api/forecast", params={"horizon": 60}, json={"plaisir_pct": 0}).json()
    assert f["totals"]["plaisir_cents"] == 0 and f["end_balance_cents"] > f["baseline_end_cents"]

    # Détail par catégorie : la part de chaque catégorie dans sa couche, et la catégorie « retirée » (objectif à 0).
    f = c.post("/api/forecast", params={"horizon": 60}, json={"targets": {str(cats["Bars"]["id"]): 0}}).json()
    by_cat = {x["category_id"]: x for x in f["categories"]}
    assert set(by_cat) == {cats["Courses"]["id"], cats["Bars"]["id"]}
    assert by_cat[cats["Bars"]["id"]]["amount_cents"] == 0 and by_cat[cats["Bars"]["id"]]["base_amount_cents"] > 0
    assert by_cat[cats["Bars"]["id"]]["layer"] == "plaisir" and f["totals"]["plaisir_cents"] == 0
    assert abs(by_cat[cats["Courses"]["id"]]["amount_cents"] - f["totals"]["essentiel_cents"]) <= 1

    # Nature réglée par l'utilisateur : les courses passent en « plaisir ».
    courses_id = cats["Courses"]["id"]
    assert c.patch(f"/api/categories/{courses_id}", json={"nature": "plaisir"}).json()["nature_effective"] == "plaisir"
    assert c.get("/api/projection", params={"months": 3}).json()["model"]["layers"]["essentiel"]["trend_cents"] == 0
    assert c.patch(f"/api/categories/{courses_id}", json={"nature": "auto"}).json()["nature_effective"] == "essentiel"
    assert c.patch(f"/api/categories/{cats['Salaire']['id']}", json={"nature": "fixe"}).status_code == 422
    assert c.get("/api/projection", params={"until": "2000-01"}).status_code == 422


def test_salary_paid_early_is_expected_on_its_latest_usual_day(auth_client):
    import calendar

    c = auth_client
    acc, cats, op = _setup(c)
    first = date.today().replace(day=1)
    for i, day in enumerate([25, 28, 26, 27]):
        month = add_months(first, i - 4)
        op(month.replace(day=day), 210000, f"SOCIETE INVENTEE REF {i}", merchant=f"Société inventée {i}")  # libellé différent chaque mois
    c.post("/api/recurring/refresh")
    rec = c.get("/api/recurring").json()["items"]
    salary = [i for i in rec if i["kind"] == "revenu"]
    assert len(salary) == 1 and salary[0]["basis"] in ("montant", "categorie")
    f = c.get("/api/forecast", params={"horizon": 70}).json()
    dates = [date.fromisoformat(e["date"]) for e in f["events"] if e["series_id"] == salary[0]["id"]]
    assert dates and all(d.day == min(28, calendar.monthrange(d.year, d.month)[1]) or d == date.today() for d in dates)
    assert all(e["kind"] == "revenu" for e in f["events"] if e["series_id"] == salary[0]["id"])
