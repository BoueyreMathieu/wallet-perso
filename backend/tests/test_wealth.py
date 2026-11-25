"""Calculs de patrimoine (pur Python, montants inventés)."""

from datetime import date

from app.wealth import computed_value, depreciated_value, loan_remaining, loan_schedule, monthly_payment, yearly_interest


def test_depreciation():
    assert depreciated_value(2000000, date(2024, 1, 1), 15, date(2024, 1, 1)) == 2000000
    v = depreciated_value(2000000, date(2024, 1, 1), 15, date(2026, 1, 1))
    assert abs(v - round(2000000 * 0.85 ** (731 / 365.25))) <= 1 and 1440000 < v < 1450000
    assert depreciated_value(100000, date(2024, 1, 1), 0, date(2030, 1, 1)) == 100000


def test_loan_schedule_and_remaining():
    # 10 000 € à 3,6 % sur 24 mois.
    pay = monthly_payment(1000000, 3.6, 24)
    assert 43200 <= pay <= 43300
    sched = loan_schedule(1000000, 3.6, 24, date(2026, 1, 5))
    assert len(sched) == 24 and sched[-1].remaining_cents == 0 and sched[0].interest_cents == 3000
    assert sum(i.principal_cents for i in sched) == 1000000
    assert loan_remaining(1000000, 3.6, 24, date(2026, 1, 5), date(2026, 1, 4)) == 1000000
    assert loan_remaining(1000000, 3.6, 24, date(2026, 1, 5), date(2026, 3, 5)) == sched[2].remaining_cents
    assert monthly_payment(120000, 0, 12) == 10000  # prêt à taux zéro


def test_savings_and_computed_values():
    assert yearly_interest(1000000, 2.4) == 24000
    assert yearly_interest(3000000, 2.4, ceiling_cents=2295000) == round(2295000 * 0.024)
    assert computed_value("courant", {"rate_pct": 1}, date(2026, 1, 1)) is None
    assert computed_value("bien", {"purchase_cents": 100000, "purchase_date": "2026-01-01", "depreciation_pct": 10}, date(2026, 1, 1)) == 100000
    assert computed_value("credit", {"principal_cents": 120000, "rate_pct": 0, "months": 12, "first_payment": "2026-01-10"}, date(2026, 2, 10)) == -100000
