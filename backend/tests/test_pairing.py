"""Rapprochement partiel prélèvement bancaire ↔ achat PayPal (pur Python, montants inventés)."""

from datetime import date

from app.pairing import Cand, partial_pairs


def d(day: int) -> date:
    return date(2026, 11, day)


def test_bank_debit_smaller_than_purchase_is_paired():
    # Achat de 20 €, dont 7,70 € pris sur le solde PayPal : la banque n'a prélevé que 12,30 €.
    assert partial_pairs([Cand(1, d(3), -1230)], [Cand(10, d(1), -2000)]) == [(1, 10)]


def test_purchase_must_be_bigger_and_in_the_window():
    assert partial_pairs([Cand(1, d(3), -1230)], [Cand(10, d(1), -1000)]) == []  # plus petit : pas un complément
    assert partial_pairs([Cand(1, d(3), -1230)], [Cand(10, d(1), -1230)]) == []  # égal : cas déjà traité ailleurs
    assert partial_pairs([Cand(1, d(20), -1230)], [Cand(10, d(1), -2000)]) == []  # trop ancien
    assert partial_pairs([Cand(1, d(3), -1230)], [Cand(10, d(9), -2000)]) == []  # trop récent


def test_ambiguity_is_not_guessed():
    two_same_day = [Cand(10, d(2), -2000), Cand(11, d(2), -3000)]
    assert partial_pairs([Cand(1, d(3), -1230)], two_same_day) == []
    # À distances différentes, le plus proche gagne.
    assert partial_pairs([Cand(1, d(3), -1230)], [Cand(10, d(2), -2000), Cand(11, d(1), -3000)]) == [(1, 10)]


def test_each_purchase_is_used_once():
    banks = [Cand(1, d(3), -1230), Cand(2, d(4), -500)]
    pairs = partial_pairs(banks, [Cand(10, d(3), -2000)])
    assert pairs == [(1, 10)]  # le plus proche (même jour) l'emporte, l'autre prélèvement reste libre


def test_credits_are_ignored():
    assert partial_pairs([Cand(1, d(3), 1230)], [Cand(10, d(1), -2000)]) == []
