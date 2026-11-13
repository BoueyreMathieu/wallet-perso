"""Conseils d'optimisation : règles pures (données inventées)."""

from datetime import date

from app.advice import CatTrend, Context, Series, SmallSpender, advise, euros


def _ids(ctx):
    return {a.id: a for a in advise(ctx)}


def test_euros_format():
    assert euros(123456) == "1 235 €" and euros(-999) == "9,99 €" and euros(5000) == "50 €"


def test_spending_rules():
    ctx = Context(
        today=date(2026, 11, 13),
        trends=[
            CatTrend(1, "Courses", "essentiel", 40000, [30000, 30000, 30000, 38000, 40000, 42000]),
            CatTrend(2, "Bars", "plaisir", 9000, [5000, 5000, 5000, 9000, 9000, 9000]),
            CatTrend(3, "Livraison", "plaisir", 8000, [8000] * 6),
            CatTrend(4, "Loyer / crédit", "fixe", 80000, [70000, 70000, 70000, 80000, 80000, 80000]),
        ],
        small=[SmallSpender("Boulangerie inventée", 5, 14, 4900), SmallSpender("Kiosque inventé", 6, 3, 900)],
    )
    a = _ids(ctx)
    assert a["derive:1"].gain_monthly_cents == 10000 and a["derive:1"].action["scenario"]["targets"] == {"1": 30000}
    assert "derive:4" not in a  # les charges fixes ne « dérivent » pas (elles ont leur propre suivi)
    assert a["plaisirs:hausse"].gain_monthly_cents == 4000
    assert a["livraison"].action["scenario"]["targets"] == {"3": 4000}
    assert "petits:Boulangerie inventée" in a and "petits:Kiosque inventé" not in a


def test_subscriptions_and_money_rules():
    today = date(2026, 11, 13)
    ctx = Context(
        today=today,
        series=[
            Series(1, "Vidéo inventée", "Streaming", -1349, 1349, False, "actif", -1099, date(2026, 10, 2)),
            Series(2, "Autre vidéo inventée", "Streaming", -899, 899, False, "actif"),
            Series(3, "Vieux service inventé", "Presse", -500, 500, False, "actif", maybe_ended=True),
            Series(4, "Ancienne hausse", "Musique", -1199, 1199, False, "actif", -999, date(2025, 1, 2)),
        ],
        liquid_balance=600000, has_savings_account=True, monthly_spending=200000,
        income_months=[250000, 250000, 250000], spending_months=[240000, 245000, 238000],
        fees_3_months=2400, lowest_30_days=-15000, lowest_date=date(2026, 11, 27),
        uncategorized=12, to_confirm=2, consent_days_left=[("Banque inventée", 5)],
    )
    items = advise(ctx)
    a = {x.id: x for x in items}
    assert items[0].id == "decouvert"  # alertes d'abord
    assert a["hausse_prix:1"].gain_monthly_cents == 250 and "hausse_prix:4" not in a  # hausse trop ancienne
    assert a["doublon:Streaming"].gain_monthly_cents == 899
    assert "fini:3" in a
    assert a["argent_qui_dort"].gain_monthly_cents == round(300000 * 0.015 / 12)
    assert a["frais"].gain_monthly_cents == 800
    assert a["taux_epargne"].action["scenario"]["extra_saving_cents"] == 25000
    assert {"a_categoriser", "a_confirmer", "consentement:Banque inventée"} <= set(a)


def test_nothing_to_say():
    assert advise(Context(today=date(2026, 11, 13))) == []


def test_advice_api_and_dismiss(auth_client):
    from datetime import timedelta

    c = auth_client
    acc = c.post("/api/accounts", json={"name": "Courant inventé", "type": "courant", "initial_balance_cents": 50000}).json()
    today = date.today()
    for i in range(14):  # 14 petits passages en 30 jours
        r = c.post("/api/transactions", json={"account_id": acc["id"], "booked_at": (today - timedelta(days=2 * i)).isoformat(),
                                               "amount_cents": -450, "label": "CB BOULANGERIE INVENTEE", "merchant": "Boulangerie inventée"})
        assert r.status_code == 201
    items = c.get("/api/advice").json()["items"]
    ids = {a["id"] for a in items}
    assert "petits:Boulangerie inventée" in ids
    assert c.post("/api/advice/dismiss", json={"id": "petits:Boulangerie inventée", "days": 30}).json() == {"ok": True}
    assert "petits:Boulangerie inventée" not in {a["id"] for a in c.get("/api/advice").json()["items"]}
