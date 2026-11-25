"""Contrôle de cohérence des soldes (pur Python, montants inventés)."""

from datetime import date

from app.balance_check import balance_gap


def d(day: int) -> date:
    return date(2026, 11, day)


def test_consistent_account_has_no_gap():
    snaps = [(d(1), 100000), (d(10), 95000)]
    ops = [(d(3), -2000), (d(7), -3000), (d(1), -999)]  # l'opération du 1er est déjà dans le premier solde
    g = balance_gap(snaps, ops, d(1))
    assert g is not None and g.gap_cents == 0 and (g.since, g.until) == (d(1), d(10))


def test_missing_operation_is_reported():
    snaps = [(d(1), 100000), (d(10), 95000)]
    ops = [(d(3), -2000)]  # il manque 30 € de dépenses
    assert balance_gap(snaps, ops, d(1)).gap_cents == -3000


def test_one_day_offset_is_tolerated():
    # La banque arrête son solde la veille : l'opération du 10 n'y est pas encore.
    snaps = [(d(1), 100000), (d(10), 98000)]
    ops = [(d(5), -2000), (d(10), -500)]
    assert balance_gap(snaps, ops, d(1)).gap_cents == 0


def test_needs_two_balances_in_the_period():
    assert balance_gap([(d(1), 100000)], [], d(1)) is None
    assert balance_gap([(d(1), 1), (d(5), 2)], [], d(2)) is None
