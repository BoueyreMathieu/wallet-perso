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


def test_trend_level_follows_a_clear_change_of_rhythm():
    from app.trends import trend_level, weighted_level

    steady = [30000, 31000, 29000, 30000, 30500, 29500]
    assert trend_level(steady) == weighted_level(steady)
    moved = [30000, 31000, 29000, 30000, 45000, 47000]  # nouveau logement, nouvelles habitudes
    assert trend_level(moved) > weighted_level(moved) and abs(trend_level(moved) - 46000) < 3000
    assert trend_level([30000, 45000, 47000]) == weighted_level([30000, 45000, 47000])  # trop peu de mois


def test_band_from_good_and_bad_months():
    from app.trends import band

    assert band([100, 100], 100) == (0.85, 1.15)
    lo, hi = band([80, 90, 100, 110, 120, 130, 100, 95], 100)
    assert 0.8 <= lo <= 1.0 <= hi <= 1.3


def test_habit_places_a_weekly_shop_on_its_day():
    from datetime import date, timedelta

    from app.trends import Profile, learn_habit, unit_expected

    today = date(2026, 11, 13)  # un vendredi
    saturdays = [today - timedelta(days=6 + 7 * i) for i in range(12)]
    h = learn_habit(1, "Supermarché inventé", [(d, 7000) for d in saturdays], today)
    assert h is not None and h.amount == 7000 and max(range(7), key=lambda i: h.weekday[i]) == 5
    assert abs(h.monthly - 12 / 13 * 7000 * 52.18 / 12) < 1
    # Pas assez de passages, ou plus fréquenté : pas une habitude.
    assert learn_habit(1, "x", [(d, 7000) for d in saturdays[:4]], today) is None
    assert learn_habit(1, "x", [(d - timedelta(days=30), 7000) for d in saturdays], today) is None

    days = unit_expected(40000, [h], Profile(), date(2026, 12, 1), date(2026, 12, 31))
    # Le niveau de la catégorie est respecté, au nombre de samedis du mois près (décembre 2026 n'en a que 4).
    assert abs(sum(days.values()) - 40000) < 0.06 * 40000
    sat = [v for d, v in days.items() if d.weekday() == 5]
    tue = [v for d, v in days.items() if d.weekday() == 1]
    assert min(sat) > 4 * max(tue)  # les courses tombent le samedi


def test_rest_of_month_uses_what_is_already_spent():
    from app.trends import rest_of_month

    # Déjà 350 € de courses sur 400 € habituels, mi-mois : il en reste peu (au moins 30 % du reste habituel).
    assert rest_of_month(200, 400, 350, 200) == 60
    assert rest_of_month(200, 400, 250, 200) == 150  # un peu en avance : 400 − 250
    # En retard sur son rythme (rien dépensé à mi-mois) : reste habituel + la moitié de l'écart.
    assert rest_of_month(200, 400, 0, 200) == 300
