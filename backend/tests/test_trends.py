"""Tendances de dépenses (sans base, données inventées)."""

from datetime import date, timedelta

from app.trends import Profile, apply_caps, direction, expected_between, learn_profile, month_weights, weighted_level, winsorize


def test_weighted_level_uses_all_months_with_more_weight_on_recent():
    # Tous les mois comptent : pas seulement le dernier.
    level = weighted_level([30000, 30000, 30000, 30000, 30000, 10000])
    assert 20000 < level < 30000
    assert weighted_level([20000] * 12) == 20000
    assert weighted_level([]) == 0


def test_outlier_month_is_capped():
    assert winsorize([10000, 12000, 11000, 90000]) == [10000, 12000, 11000, 34500]
    assert weighted_level([10000, 12000, 11000, 90000]) < 25000


def test_direction():
    assert direction([100, 100, 100, 150, 150, 150]) == "hausse"
    assert direction([200, 200, 200, 100, 100, 100]) == "baisse"
    assert direction([100, 100, 100]) == "stable"


def test_profile_learns_weekend_spending_and_distribution_sums_to_monthly():
    start = date(2026, 1, 1)
    saturdays = [start + timedelta(days=i) for i in range(300) if (start + timedelta(days=i)).weekday() == 5]
    p = learn_profile([(d, 5000) for d in saturdays], months=10)
    assert p.weekday[5] > 4 and p.weekday[0] < 0.5
    weights = month_weights(2026, 11, p)
    assert abs(sum(weights.values()) - 1) < 1e-9
    days = expected_between(30000, date(2026, 11, 1), date(2026, 11, 30), p)
    assert abs(sum(days.values()) - 30000) < 1
    assert days[date(2026, 11, 7)] > days[date(2026, 11, 9)]  # samedi > lundi
    # Peu d'historique : profil proche de l'uniforme.
    assert learn_profile([(d, 5000) for d in saturdays[:4]], months=1).weekday[0] > 0.5
    assert Profile().weekday == [1.0] * 7


def test_apply_caps():
    parents = {1: None, 2: 1, 3: 1, 4: None}
    units = {1: 0.0, 2: 30000.0, 3: 10000.0, 4: 5000.0, None: 2000.0}
    # Budget sur la catégorie principale : sous-catégories réduites proportionnellement.
    out = apply_caps(units, parents, {1: 20000})
    assert round(out[2]) == 15000 and round(out[3]) == 5000 and out[4] == 5000 and out[None] == 2000
    # Budget sur une sous-catégorie, plus haut que la tendance sur une autre : sans effet.
    out = apply_caps(units, parents, {3: 4000, 4: 9000})
    assert out[3] == 4000 and out[2] == 30000 and out[4] == 5000
