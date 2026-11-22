import pytest

from app.core.campaign_rules import (
    RULE_DEFINITIONS,
    default_campaign_rule_values,
    validate_campaign_rule_values,
)


EXPECTED_GAMEPLAY_KEYS = set(
    """
    CAMPAIGN_STARTING_INFLUENCE
    CAMPAIGN_STARTING_GOLD
    CAMPAIGN_STARTING_IRON
    CAMPAIGN_STARTING_WOOD
    CAMPAIGN_STARTING_FOOD
    CAMPAIGN_STARTING_MITHRIL
    CLAN_ATTACK_COOLDOWN_HOURS
    WAR_DURATION_HOURS
    WAR_ELO_BASE_POINTS
    WAR_ELO_MIN_POINTS
    WAR_ELO_MAX_POINTS
    WAR_ELO_MIN_DRAW_POINTS
    WAR_ELO_MAX_DRAW_POINTS
    WAR_TEAM_SIZE_BONUS_STEP_PERCENT
    WAR_FULL_CLAN_TEAM_BONUS_PERCENT
    WAR_MODIFIER_CAP_PERCENT
    WAR_MIN_MATCH_DURATION_SECONDS
    TERRITORY_LEVEL_BONUS_PERCENT
    CLAN_JOIN_TIMEOUT_HOURS
    TERRITORY_RESOURCE_PAYOUT_HOURS
    TERRITORY_RESOURCE_READY_HOURS
    TERRITORY_MAX_RESOURCE_CATCHUP_CYCLES
    NEUTRAL_CAPTURE_REQUIRED_WINS
    WAR_VICTORY_INFLUENCE_BASE
    WAR_VICTORY_STRATEGIC_MULTIPLIER
    WAR_POWER_BONUS_CAP_POINTS
    WAR_POWER_POINTS_DIVISOR
    ATTACK_INFLUENCE_NEUTRAL_BASE
    ATTACK_INFLUENCE_OWNED_BASE
    ATTACK_INFLUENCE_STRATEGIC_MULTIPLIER
    ATTACK_INFLUENCE_FORTIFICATION_MULTIPLIER
    ECONOMY_TICK_HOURS
    ECONOMY_MAX_CATCHUP_DAYS
    TERRITORY_RESOURCE_WEALTH_DIVISOR
    TERRITORY_MIN_RESOURCE_OUTPUT
    TERRITORY_MAX_UPGRADE_LEVEL
    TERRITORY_MAX_UPGRADE_LEVELS_PER_PURCHASE
    POPULATION_BASE_GOLD_COST
    POPULATION_GOLD_COST_PER_LEVEL
    POPULATION_GOLD_COST_WEALTH_PERCENT
    POPULATION_BASE_WOOD_COST
    POPULATION_WOOD_LEVEL_DIVISOR
    POPULATION_DEVELOPMENT_BONUS_FIRST_LEVELS_PERCENT
    POPULATION_DEVELOPMENT_BONUS_LATER_LEVELS_PERCENT
    POPULATION_DEVELOPMENT_BONUS_BREAK_LEVEL
    FORTIFICATION_BASE_GOLD_COST
    FORTIFICATION_GOLD_COST_PER_LEVEL
    FORTIFICATION_BASE_IRON_COST
    FORTIFICATION_MITHRIL_START_LEVEL
    OFFENSE_BASE_GOLD_COST
    OFFENSE_GOLD_COST_PER_LEVEL
    OFFENSE_BASE_IRON_COST
    OFFENSE_FOOD_LEVEL_DIVISOR
    PORT_LEVEL_BONUS_PERCENT
    PORT_BASE_GOLD_COST
    PORT_GOLD_COST_PER_LEVEL
    PORT_BASE_WOOD_COST
    PORT_WOOD_LEVEL_DIVISOR
    PORT_BASE_IRON_COST
    FLEET_LEVEL_BONUS_PERCENT
    FLEET_BASE_GOLD_COST
    FLEET_GOLD_COST_PER_LEVEL
    FLEET_BASE_WOOD_COST
    FLEET_WOOD_LEVEL_DIVISOR
    FLEET_BASE_IRON_COST
    FLEET_IRON_LEVEL_DIVISOR
    FLEET_BASE_FOOD_COST
    POPULATION_BASE_GROWTH_PERCENT
    POPULATION_GROWTH_RELIC_DIVISOR
    POPULATION_FLAT_GROWTH_PER_LEVEL
    POPULATION_MAXIMUM
    POPULATION_INCOME_BONUS_CAP_PERCENT
    POPULATION_PER_INCOME_PERCENT
    RELIC_LEVEL_1_COST_MULTIPLIER
    RELIC_LEVEL_2_COST_MULTIPLIER
    RELIC_LEVEL_3_COST_MULTIPLIER
    CARAVAN_HOURS_PER_STEP
    CARAVAN_SEA_HOURS_PER_STEP
    CARAVAN_MIN_GOLD_FEE
    CARAVAN_BASE_GOLD_FEE
    CARAVAN_DISTANCE_GOLD_FEE
    CARAVAN_VOLUME_STEP
    CARAVAN_VOLUME_GOLD_FEE
    CARAVAN_GOLD_FEE_MULTIPLIER_PERCENT
    ELO_START_RATING
    ELO_PROVISIONAL_MATCHES
    ELO_PROVISIONAL_K
    ELO_REGULAR_K
    CLAN_ACTIVITY_WINDOW_DAYS
    CLAN_ACTIVITY_MIN_MATCHES
    CLAN_ATTACK_SQUAD_MIN_MEMBERS
    CLAN_LEVEL_1_ATTACK_CAPACITY
    CLAN_LEVEL_2_ACTIVE_MEMBERS
    CLAN_LEVEL_2_TERRITORIES
    CLAN_LEVEL_2_INFLUENCE
    CLAN_LEVEL_2_ATTACK_CAPACITY
    CLAN_LEVEL_3_ACTIVE_MEMBERS
    CLAN_LEVEL_3_TERRITORIES
    CLAN_LEVEL_3_INFLUENCE
    CLAN_LEVEL_3_ATTACK_CAPACITY
    CLAN_LEVEL_4_ACTIVE_MEMBERS
    CLAN_LEVEL_4_TERRITORIES
    CLAN_LEVEL_4_INFLUENCE
    CLAN_LEVEL_4_ATTACK_CAPACITY
    CLAN_LEVEL_5_ACTIVE_MEMBERS
    CLAN_LEVEL_5_TERRITORIES
    CLAN_LEVEL_5_INFLUENCE
    CLAN_LEVEL_5_ATTACK_CAPACITY
    WAR_ELO_EXPECTED_WEIGHT
    WAR_ELO_DRAW_DIVISOR
    ELO_EXPECTED_SCORE_DIVISOR
    POPULATION_WOOD_COST_PER_LEVEL
    FORTIFICATION_IRON_COST_PER_LEVEL
    FORTIFICATION_MITHRIL_COST_PER_LEVEL
    OFFENSE_IRON_COST_PER_LEVEL
    OFFENSE_BASE_FOOD_COST
    OFFENSE_FOOD_COST_PER_STEP
    PORT_WOOD_COST_PER_LEVEL
    PORT_IRON_LEVEL_DIVISOR
    PORT_IRON_COST_PER_STEP
    FLEET_WOOD_COST_PER_LEVEL
    FLEET_IRON_COST_PER_LEVEL
    FLEET_FOOD_LEVEL_DIVISOR
    FLEET_FOOD_COST_PER_STEP
    """.split()
)


def error_codes(values):
    return {error.code for error in validate_campaign_rule_values(values)}


def test_registry_contains_every_gameplay_numeric_setting():
    assert set(RULE_DEFINITIONS) == EXPECTED_GAMEPLAY_KEYS


def test_registry_defaults_match_declared_types_and_bounds():
    defaults = default_campaign_rule_values()

    assert set(defaults) == EXPECTED_GAMEPLAY_KEYS
    for key, definition in RULE_DEFINITIONS.items():
        assert definition.key == key
        assert definition.value_type in {"int", "float"}
        assert not isinstance(defaults[key], bool)
        expected_type = int if definition.value_type == "int" else float
        assert type(defaults[key]) is expected_type
        assert definition.minimum <= defaults[key] <= definition.maximum
        assert definition.category
        assert definition.unit
        assert definition.label_key
        assert definition.help_key


def test_registry_excludes_technical_numeric_settings():
    assert {
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "MAX_FILE_SIZE",
        "SCHEDULER_UPDATE_INTERVAL",
        "LADDER_API_SCAN_LIMIT",
        "REPLAY_MAX_FILE_SIZE",
    }.isdisjoint(RULE_DEFINITIONS)


def test_economy_v2_defaults_match_agreed_balance():
    values = default_campaign_rule_values()

    assert values["CLAN_ACTIVITY_WINDOW_DAYS"] == 28
    assert values["CLAN_ACTIVITY_MIN_MATCHES"] == 3
    assert values["CLAN_ATTACK_SQUAD_MIN_MEMBERS"] == 5
    assert [
        values[f"CLAN_LEVEL_{level}_ATTACK_CAPACITY"] for level in range(1, 6)
    ] == [1, 2, 3, 4, 5]
    assert [
        (
            values[f"CLAN_LEVEL_{level}_ACTIVE_MEMBERS"],
            values[f"CLAN_LEVEL_{level}_TERRITORIES"],
            values[f"CLAN_LEVEL_{level}_INFLUENCE"],
        )
        for level in range(2, 6)
    ] == [(11, 2, 140), (17, 4, 230), (22, 6, 340), (30, 10, 500)]
    assert values["TERRITORY_RESOURCE_READY_HOURS"] == 48
    assert values["TERRITORY_RESOURCE_PAYOUT_HOURS"] == 24
    assert values["TERRITORY_MAX_RESOURCE_CATCHUP_CYCLES"] == 14
    assert values["POPULATION_BASE_GROWTH_PERCENT"] == 4
    assert values["POPULATION_FLAT_GROWTH_PER_LEVEL"] == 20
    assert values["POPULATION_MAXIMUM"] == 4_000
    assert values["POPULATION_INCOME_BONUS_CAP_PERCENT"] == 20
    assert values["POPULATION_PER_INCOME_PERCENT"] == 100
    assert values["CAMPAIGN_STARTING_GOLD"] == 100
    assert values["CAMPAIGN_STARTING_IRON"] == 6
    assert values["CAMPAIGN_STARTING_WOOD"] == 6
    assert values["CAMPAIGN_STARTING_FOOD"] == 3
    assert values["CAMPAIGN_STARTING_MITHRIL"] == 0
    assert values["POPULATION_BASE_GOLD_COST"] == 100
    assert values["POPULATION_GOLD_COST_PER_LEVEL"] == 25
    assert values["POPULATION_GOLD_COST_WEALTH_PERCENT"] == 100
    assert values["POPULATION_BASE_WOOD_COST"] == 1
    assert values["POPULATION_WOOD_LEVEL_DIVISOR"] == 2
    assert values["POPULATION_DEVELOPMENT_BONUS_FIRST_LEVELS_PERCENT"] == 8
    assert values["POPULATION_DEVELOPMENT_BONUS_LATER_LEVELS_PERCENT"] == 4
    assert values["POPULATION_DEVELOPMENT_BONUS_BREAK_LEVEL"] == 5
    assert values["FORTIFICATION_BASE_GOLD_COST"] == 100
    assert values["FORTIFICATION_GOLD_COST_PER_LEVEL"] == 30
    assert values["OFFENSE_BASE_GOLD_COST"] == 100
    assert values["OFFENSE_GOLD_COST_PER_LEVEL"] == 30
    assert values["PORT_BASE_GOLD_COST"] == 50
    assert values["PORT_GOLD_COST_PER_LEVEL"] == 15
    assert values["PORT_BASE_WOOD_COST"] == 0
    assert values["PORT_WOOD_LEVEL_DIVISOR"] == 5
    assert values["PORT_IRON_LEVEL_DIVISOR"] == 5
    assert values["FLEET_BASE_GOLD_COST"] == 50
    assert values["FLEET_GOLD_COST_PER_LEVEL"] == 15
    assert values["FLEET_BASE_WOOD_COST"] == 0
    assert values["FLEET_WOOD_LEVEL_DIVISOR"] == 5
    assert values["FLEET_IRON_LEVEL_DIVISOR"] == 5
    assert values["FLEET_BASE_FOOD_COST"] == 0
    assert values["FLEET_FOOD_LEVEL_DIVISOR"] == 5
    assert [
        values[key]
        for key in (
            "CARAVAN_HOURS_PER_STEP",
            "CARAVAN_MIN_GOLD_FEE",
            "CARAVAN_BASE_GOLD_FEE",
            "CARAVAN_DISTANCE_GOLD_FEE",
            "CARAVAN_VOLUME_STEP",
            "CARAVAN_VOLUME_GOLD_FEE",
        )
    ] == [6, 10, 7, 4, 7, 1]
    assert values["CARAVAN_SEA_HOURS_PER_STEP"] == 8
    assert values["CARAVAN_GOLD_FEE_MULTIPLIER_PERCENT"] == 100


def test_default_campaign_rules_are_valid():
    assert validate_campaign_rule_values(default_campaign_rule_values()) == []


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ({"WAR_ELO_MIN_POINTS": 16}, "range_order"),
        ({"WAR_ELO_MIN_DRAW_POINTS": 9}, "range_order"),
        ({"WAR_POWER_POINTS_DIVISOR": 0}, "positive_required"),
        ({"ELO_PROVISIONAL_K": 10}, "range_order"),
        ({"CLAN_LEVEL_4_TERRITORIES": 2}, "level_order"),
        ({"CLAN_LEVEL_1_ATTACK_CAPACITY": 0}, "positive_required"),
        ({"CLAN_ATTACK_SQUAD_MIN_MEMBERS": 0}, "positive_required"),
    ],
)
def test_cross_field_validation_rejects_invalid_values(mutation, expected_code):
    values = default_campaign_rule_values()
    values.update(mutation)

    assert expected_code in error_codes(values)


def test_validation_rejects_missing_unknown_wrong_type_and_out_of_bounds_values():
    missing = default_campaign_rule_values()
    missing.pop("WAR_DURATION_HOURS")
    unknown = {**default_campaign_rule_values(), "UNKNOWN_RULE": 1}
    wrong_type = {**default_campaign_rule_values(), "WAR_DURATION_HOURS": 96.0}
    out_of_bounds = {**default_campaign_rule_values(), "WAR_DURATION_HOURS": -1}

    assert "missing" in error_codes(missing)
    assert "unknown" in error_codes(unknown)
    assert "type" in error_codes(wrong_type)
    assert "bounds" in error_codes(out_of_bounds)
