"""Objectifs d'épargne et patrimoine prévu (données inventées)."""

from datetime import date, timedelta

from app.recurrence import add_months
from app.services.goals import months_between


def test_months_between():
    assert months_between(date(2026, 11, 13), date(2027, 6, 30)) == 8
    assert months_between(date(2026, 11, 13), date(2026, 11, 20)) == 1


def test_goals_on_an_account_and_by_hand(auth_client):
    c = auth_client
    livret = c.post("/api/accounts", json={"name": "Livret inventé", "type": "epargne", "initial_balance_cents": 300000}).json()
    first = date.today().replace(day=1)
    for k in (1, 2, 3):  # 200 € arrivent chaque mois sur le livret
        c.post("/api/transactions", json={"account_id": livret["id"], "booked_at": (add_months(first, -k) + timedelta(days=4)).isoformat(),
                                          "amount_cents": 20000, "label": "VIR EPARGNE INVENTEE"})
    in_a_year = add_months(date.today(), 12)
    trip = c.post("/api/goals", json={"name": "Voyage inventé", "icon": "✈️", "target_cents": 200000, "account_id": livret["id"]}).json()
    car = c.post("/api/goals", json={"name": "Voiture inventée", "target_cents": 500000, "account_id": livret["id"],
                                     "target_date": in_a_year.isoformat(), "priority": 1}).json()
    hand = c.post("/api/goals", json={"name": "Cadeau inventé", "target_cents": 10000, "saved_cents": 2500}).json()
    assert trip["current_cents"] == 200000 and trip["status"] == "atteint"
    # Le reste du livret (100 €) va à la voiture ; 4 000 € à trouver en 12 mois.
    assert car["current_cents"] == 100000 and car["monthly_needed_cents"] == -(-400000 // 12) and car["monthly_rate_cents"] == 20000
    assert car["status"] == "en_retard"  # à 200 €/mois il faut 20 mois
    assert hand["current_cents"] == 2500 and hand["remaining_cents"] == 7500 and hand["eta"] is None
    assert c.patch(f"/api/goals/{hand['id']}", json={"saved_cents": 10000}).json()["status"] == "atteint"
    assert c.post("/api/goals", json={"name": "X", "target_cents": 100, "account_id": 999999}).status_code == 422
    assert c.delete(f"/api/goals/{hand['id']}").json() == {"ok": True}
    assert len(c.get("/api/goals").json()) == 2

    # Patrimoine prévu : le livret (hors comptes du quotidien) rapporte et reçoit l'épargne.
    p = c.post("/api/projection", params={"months": 3, "rate": 0}, json={}).json()
    assert p["net_worth_start_cents"] == 300000 and p["months"][-1]["net_worth_cents"] >= 300000
