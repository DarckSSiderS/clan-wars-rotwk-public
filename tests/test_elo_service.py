from app.services.elo_service import (
    PATCH_202,
    PATCH_ENNORATH,
    draw_territory_points,
    expected_score,
    get_patch_family,
    k_factor,
    winner_territory_points,
)
from app.core.campaign_rules import default_campaign_rule_values


RULES = default_campaign_rule_values()


def test_patch_families_are_kept_separate():
    assert get_patch_family("Patch 2.02 (9.7.7)") == PATCH_202
    assert get_patch_family("Ennorath (1.9.7.7d)") == PATCH_ENNORATH
    assert get_patch_family(None, "official-2:9.7.7") == PATCH_202
    assert get_patch_family("Edain Unchained") is None


def test_equal_ratings_award_ten_points():
    probability = expected_score(1200, 1200, RULES)
    assert probability == 0.5
    assert winner_territory_points(probability, RULES) == 10


def test_favorite_and_underdog_points_are_clamped_to_small_scale():
    favorite_probability = expected_score(1600, 1000, RULES)
    underdog_probability = expected_score(1000, 1600, RULES)

    assert winner_territory_points(favorite_probability, RULES) == 5
    assert winner_territory_points(underdog_probability, RULES) == 15


def test_draw_support_stays_server_side_and_in_small_scale():
    assert draw_territory_points(0.5, RULES) == 5
    assert 3 <= draw_territory_points(0.95, RULES) <= 8
    assert 3 <= draw_territory_points(0.05, RULES) <= 8


def test_elo_calculations_use_the_supplied_rule_snapshot():
    rules = {
        **RULES,
        "ELO_EXPECTED_SCORE_DIVISOR": 200,
        "WAR_ELO_BASE_POINTS": 20,
        "WAR_ELO_MIN_POINTS": 1,
        "WAR_ELO_MAX_POINTS": 100,
        "WAR_ELO_EXPECTED_WEIGHT": 2.0,
        "ELO_PROVISIONAL_MATCHES": 5,
        "ELO_PROVISIONAL_K": 60,
        "ELO_REGULAR_K": 12,
    }

    probability = expected_score(1000, 1200, rules)
    assert probability == 1 / 11
    assert winner_territory_points(probability, rules) == 38
    assert k_factor(4, rules) == 60
    assert k_factor(5, rules) == 12
