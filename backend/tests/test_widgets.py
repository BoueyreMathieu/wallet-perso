"""Résumé des widgets Android (données inventées)."""

from datetime import date, timedelta

from app.recurrence import add_months


def _token(client) -> dict:
    token = client.post("/api/auth/device", json={"password": "test-password", "name": "Pixel inventé"}).json()["token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def test_widget_summary_v2(auth_client):
    c = auth_client
    cats = {x["name"]: x["id"] for x in c.get("/api/categories").json()}
    acc = c.post("/api/accounts", json={"name": "Courant inventé", "type": "courant", "initial_balance_cents": 100000}).json()
    livret = c.post("/api/accounts", json={"name": "Livret inventé", "type": "epargne", "initial_balance_cents": 50000}).json()
    today = date.today()

    def op(day, amount, label, category=None, account=acc, merchant=None):
        r = c.post("/api/transactions", json={
            "account_id": account["id"], "booked_at": day.isoformat(), "amount_cents": amount, "label": label,
            "category_id": category, "merchant": merchant,
        })
        assert r.status_code == 201, r.text

    op(today, -2500, "RESTAURANT INVENTE", cats["Restaurants"])
    op(today, -4000, "SUPERMARCHE INVENTE", cats["Courses"])
    # Abonnement mensuel : 4 échéances passées, la prochaine dans le mois qui vient.
    base = today - timedelta(days=3)
    for i in range(4, 0, -1):
        op(add_months(base, -i), -1599, "PRLV STREAMING INVENTE", cats["Abonnements"], merchant="Streaming inventé")
    c.post("/api/recurring/refresh")
    assert c.put(f"/api/budgets/{cats['Restaurants']}", json={"monthly_amount_cents": 3000}).status_code == 200

    h = _token(c)
    s = c.get("/api/widgets/summary", headers=h).json()
    assert s["version"] == 2

    # Comptes : identifiant, mouvements du mois, dernières opérations.
    courant = next(a for a in s["accounts"] if a["name"] == "Courant inventé")
    assert courant["id"] == acc["id"] and courant["month_out_cents"] >= 6500 and courant["month_in_cents"] == 0
    assert courant["recent"][0]["amount_cents"] in (-2500, -4000) and len(courant["recent"]) == 5
    assert next(a for a in s["accounts"] if a["id"] == livret["id"])["balance_cents"] == 50000
    assert s["net_worth_change_cents"] <= -6500

    # Couches du mois et catégories.
    assert s["layers"]["plaisir"] >= 2500 and s["layers"]["essentiel"] >= 4000
    assert sum(s["layers"].values()) == s["spent_cents"]
    assert s["top_categories"] and s["top_categories"][0]["spent_cents"] > 0

    # Budget, fin du mois, échéances.
    [b] = s["budgets"]
    assert b["name"] == "Restaurants" and b["spent_cents"] == 2500 and b["level"] in ("ok", "alerte")
    eom = s["end_of_month"]
    assert eom is not None and eom["start_cents"] == courant["balance_cents"]
    assert len(eom["points"]) == (date.fromisoformat(eom["horizon"]) - today).days + 1
    assert eom["low_cents"] <= eom["start_cents"] and eom["points"][-1] == eom["balance_cents"]
    streaming = [e for e in s["upcoming"] if e["label"] == "Streaming inventé"]
    assert streaming and streaming[0]["amount_cents"] == -1599 and streaming[0]["kind"] == "depense"


def test_widget_summary_empty(client):
    h = _token(client)
    s = client.get("/api/widgets/summary", headers=h).json()
    assert s["accounts"] == [] and s["budgets"] == [] and s["upcoming"] == []
    assert s["layers"] == {"fixe": 0, "essentiel": 0, "plaisir": 0}
