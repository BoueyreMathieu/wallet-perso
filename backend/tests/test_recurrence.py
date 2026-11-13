"""Détection des récurrents (cœur sans base, données inventées)."""

import random
from datetime import date, timedelta

from app.recurrence import Point, add_months, detect, monthly_cost, next_after, occurrences

TODAY = date(2026, 11, 12)


def monthly(start: date, n: int, amount: int, first_id: int = 0) -> list[Point]:
    return [Point(first_id + i, add_months(start, i), amount) for i in range(n)]


def test_monthly_subscription():
    [d] = detect(monthly(date(2026, 1, 5), 11, -999), TODAY)
    assert d.frequency == "mensuel" and d.active and d.expected_amount_cents == -999
    assert d.next_date == date(2026, 12, 5) and len(d.ids) == 11


def test_price_increase():
    pts = monthly(date(2026, 1, 5), 7, -999) + monthly(date(2026, 8, 5), 4, -1299, first_id=100)
    [d] = detect(pts, TODAY)
    assert d.expected_amount_cents == -1299 and d.previous_amount_cents == -999 and d.price_changed_on == date(2026, 8, 5)


def test_subscription_among_one_off_purchases():
    rnd = random.Random(1)
    pts = monthly(date(2026, 2, 10), 10, -699) + [
        Point(200 + i, date(2026, 1, 1) + timedelta(days=rnd.randint(0, 300)), -rnd.randint(1500, 9000)) for i in range(15)
    ]
    [d] = detect(pts, TODAY)
    assert d.frequency == "mensuel" and d.expected_amount_cents == -699 and len(d.ids) == 10


def test_irregular_spending_is_not_recurring():
    for seed in range(200):
        rnd = random.Random(seed)
        pts = [Point(i, date(2025, 11, 1) + timedelta(days=rnd.randint(0, 375)), -rnd.randint(500, 12000)) for i in range(rnd.randint(3, 40))]
        assert detect(pts, TODAY) == [], seed


def test_variable_salary_annual_and_ended():
    rnd = random.Random(3)
    [salary] = detect([Point(i, add_months(date(2026, 1, 28), i), 210000 + rnd.randint(-15000, 15000)) for i in range(10)], TODAY)
    assert salary.frequency == "mensuel" and salary.expected_amount_cents > 0 and salary.active
    [annual] = detect([Point(1, date(2025, 3, 2), -35000), Point(2, date(2026, 3, 3), -36000)], TODAY)
    assert annual.frequency == "annuel" and annual.active and annual.next_date == date(2027, 3, 3)
    [ended] = detect(monthly(date(2025, 10, 5), 6, -1500), TODAY)
    assert not ended.active


def test_occurrences_and_costs():
    # Échéance en retard de 7 jours (tolérée) : attendue aujourd'hui, puis la suivante.
    assert occurrences(date(2026, 11, 5), "mensuel", TODAY, date(2026, 12, 31)) == [TODAY, date(2026, 12, 5)]
    assert occurrences(date(2026, 11, 20), "hebdomadaire", TODAY, date(2026, 12, 4)) == [date(2026, 11, 20), date(2026, 11, 27), date(2026, 12, 4)]
    assert next_after(date(2026, 1, 31), "mensuel") == date(2026, 2, 28)
    assert monthly_cost(-12000, "annuel") == -1000 and monthly_cost(-999, "mensuel") == -999


def test_variable_bill_among_purchases_and_regular_income():
    from app.recurrence import detect_regular_income

    rnd = random.Random(5)
    bill = [Point(i, add_months(date(2026, 1, 12), i) + timedelta(days=rnd.randint(-2, 2)), -(6000 + rnd.randint(-900, 900))) for i in range(10)]
    shop = [Point(100 + i, date(2026, 1, 1) + timedelta(days=rnd.randint(0, 300)), -rnd.randint(500, 3000)) for i in range(12)]
    [d] = detect(bill + shop, TODAY)
    assert d.frequency == "mensuel" and len(d.ids) == 10
    # Salaire versé entre le 23 et le 28, montant variable, noyé parmi d'autres virements reçus.
    salary = [Point(i, add_months(date(2026, 1, 26), i) + timedelta(days=rnd.randint(-3, 2)), 210000 + rnd.randint(-20000, 20000)) for i in range(10)]
    other = [Point(100 + i, date(2026, 1, 1) + timedelta(days=rnd.randint(0, 300)), rnd.randint(1000, 30000)) for i in range(15)]
    [inc] = detect_regular_income(salary + other, TODAY)
    assert inc.frequency == "mensuel" and len(inc.ids) == 10
    # Hasard : pas de faux revenu régulier.
    for seed in range(300):
        r = random.Random(seed)
        pts = [Point(i, date(2025, 11, 1) + timedelta(days=r.randint(0, 375)), r.randint(2000, 150000)) for i in range(r.randint(3, 40))]
        assert len(detect_regular_income(pts, TODAY)) <= 1
