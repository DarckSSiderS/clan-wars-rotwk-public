from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from app.core.section_55_balance import SECTION_55_RULE_OVERRIDES


RuleValue = int | float


@dataclass(frozen=True)
class CampaignRuleDefinition:
    key: str
    category: str
    value_type: Literal["int", "float"]
    default: RuleValue
    minimum: RuleValue
    maximum: RuleValue
    unit: str
    label_key: str
    help_key: str


@dataclass(frozen=True)
class CampaignRuleValidationError:
    code: str
    field: str | None
    message: str


_CATEGORY_DEFAULTS: dict[str, dict[str, RuleValue]] = {
    "campaign": {
        "CAMPAIGN_STARTING_INFLUENCE": 100,
        "CAMPAIGN_STARTING_GOLD": 100,
        "CAMPAIGN_STARTING_IRON": 6,
        "CAMPAIGN_STARTING_WOOD": 6,
        "CAMPAIGN_STARTING_FOOD": 3,
        "CAMPAIGN_STARTING_MITHRIL": 0,
        "CLAN_JOIN_TIMEOUT_HOURS": 72,
    },
    "war": {
        "CLAN_ATTACK_COOLDOWN_HOURS": 60,
        "WAR_DURATION_HOURS": 60,
        "WAR_ELO_BASE_POINTS": 10,
        "WAR_ELO_MIN_POINTS": 5,
        "WAR_ELO_MAX_POINTS": 15,
        "WAR_ELO_MIN_DRAW_POINTS": 3,
        "WAR_ELO_MAX_DRAW_POINTS": 8,
        "WAR_ELO_EXPECTED_WEIGHT": 1.5,
        "WAR_ELO_DRAW_DIVISOR": 2,
        "WAR_TEAM_SIZE_BONUS_STEP_PERCENT": 10,
        "WAR_FULL_CLAN_TEAM_BONUS_PERCENT": 10,
        "WAR_MODIFIER_CAP_PERCENT": 35,
        "WAR_MIN_MATCH_DURATION_SECONDS": 60,
        "NEUTRAL_CAPTURE_REQUIRED_WINS": 25,
        "WAR_VICTORY_INFLUENCE_BASE": 25,
        "WAR_VICTORY_STRATEGIC_MULTIPLIER": 5,
        "WAR_POWER_BONUS_CAP_POINTS": 3,
        "WAR_POWER_POINTS_DIVISOR": 5,
        "ATTACK_INFLUENCE_NEUTRAL_BASE": 30,
        "ATTACK_INFLUENCE_OWNED_BASE": 40,
        "ATTACK_INFLUENCE_STRATEGIC_MULTIPLIER": 8,
        "ATTACK_INFLUENCE_FORTIFICATION_MULTIPLIER": 6,
    },
    "territory": {
        "TERRITORY_LEVEL_BONUS_PERCENT": 2,
        "TERRITORY_RESOURCE_READY_HOURS": 48,
        "TERRITORY_RESOURCE_PAYOUT_HOURS": 24,
        "TERRITORY_MAX_RESOURCE_CATCHUP_CYCLES": 14,
        "TERRITORY_RESOURCE_WEALTH_DIVISOR": 25,
        "TERRITORY_MIN_RESOURCE_OUTPUT": 1,
        "TERRITORY_MAX_UPGRADE_LEVEL": 10,
        "TERRITORY_MAX_UPGRADE_LEVELS_PER_PURCHASE": 3,
    },
    "economy": {
        "ECONOMY_TICK_HOURS": 24,
        "ECONOMY_MAX_CATCHUP_DAYS": 56,
        "POPULATION_BASE_GOLD_COST": SECTION_55_RULE_OVERRIDES[
            "POPULATION_BASE_GOLD_COST"
        ],
        "POPULATION_GOLD_COST_PER_LEVEL": SECTION_55_RULE_OVERRIDES[
            "POPULATION_GOLD_COST_PER_LEVEL"
        ],
        "POPULATION_GOLD_COST_WEALTH_PERCENT": SECTION_55_RULE_OVERRIDES[
            "POPULATION_GOLD_COST_WEALTH_PERCENT"
        ],
        "POPULATION_BASE_WOOD_COST": SECTION_55_RULE_OVERRIDES[
            "POPULATION_BASE_WOOD_COST"
        ],
        "POPULATION_WOOD_COST_PER_LEVEL": SECTION_55_RULE_OVERRIDES[
            "POPULATION_WOOD_COST_PER_LEVEL"
        ],
        "POPULATION_WOOD_LEVEL_DIVISOR": 2,
        "FORTIFICATION_BASE_GOLD_COST": SECTION_55_RULE_OVERRIDES[
            "FORTIFICATION_BASE_GOLD_COST"
        ],
        "FORTIFICATION_GOLD_COST_PER_LEVEL": SECTION_55_RULE_OVERRIDES[
            "FORTIFICATION_GOLD_COST_PER_LEVEL"
        ],
        "FORTIFICATION_BASE_IRON_COST": SECTION_55_RULE_OVERRIDES[
            "FORTIFICATION_BASE_IRON_COST"
        ],
        "FORTIFICATION_IRON_COST_PER_LEVEL": SECTION_55_RULE_OVERRIDES[
            "FORTIFICATION_IRON_COST_PER_LEVEL"
        ],
        "FORTIFICATION_MITHRIL_START_LEVEL": SECTION_55_RULE_OVERRIDES[
            "FORTIFICATION_MITHRIL_START_LEVEL"
        ],
        "FORTIFICATION_MITHRIL_COST_PER_LEVEL": 1,
        "OFFENSE_BASE_GOLD_COST": SECTION_55_RULE_OVERRIDES[
            "OFFENSE_BASE_GOLD_COST"
        ],
        "OFFENSE_GOLD_COST_PER_LEVEL": SECTION_55_RULE_OVERRIDES[
            "OFFENSE_GOLD_COST_PER_LEVEL"
        ],
        "OFFENSE_BASE_IRON_COST": SECTION_55_RULE_OVERRIDES[
            "OFFENSE_BASE_IRON_COST"
        ],
        "OFFENSE_IRON_COST_PER_LEVEL": SECTION_55_RULE_OVERRIDES[
            "OFFENSE_IRON_COST_PER_LEVEL"
        ],
        "OFFENSE_BASE_FOOD_COST": SECTION_55_RULE_OVERRIDES[
            "OFFENSE_BASE_FOOD_COST"
        ],
        "OFFENSE_FOOD_LEVEL_DIVISOR": SECTION_55_RULE_OVERRIDES[
            "OFFENSE_FOOD_LEVEL_DIVISOR"
        ],
        "OFFENSE_FOOD_COST_PER_STEP": SECTION_55_RULE_OVERRIDES[
            "OFFENSE_FOOD_COST_PER_STEP"
        ],
        "PORT_LEVEL_BONUS_PERCENT": 1,
        "PORT_BASE_GOLD_COST": SECTION_55_RULE_OVERRIDES[
            "PORT_BASE_GOLD_COST"
        ],
        "PORT_GOLD_COST_PER_LEVEL": SECTION_55_RULE_OVERRIDES[
            "PORT_GOLD_COST_PER_LEVEL"
        ],
        "PORT_BASE_WOOD_COST": SECTION_55_RULE_OVERRIDES[
            "PORT_BASE_WOOD_COST"
        ],
        "PORT_WOOD_COST_PER_LEVEL": SECTION_55_RULE_OVERRIDES[
            "PORT_WOOD_COST_PER_LEVEL"
        ],
        "PORT_WOOD_LEVEL_DIVISOR": SECTION_55_RULE_OVERRIDES[
            "PORT_WOOD_LEVEL_DIVISOR"
        ],
        "PORT_BASE_IRON_COST": SECTION_55_RULE_OVERRIDES[
            "PORT_BASE_IRON_COST"
        ],
        "PORT_IRON_LEVEL_DIVISOR": SECTION_55_RULE_OVERRIDES[
            "PORT_IRON_LEVEL_DIVISOR"
        ],
        "PORT_IRON_COST_PER_STEP": SECTION_55_RULE_OVERRIDES[
            "PORT_IRON_COST_PER_STEP"
        ],
        "FLEET_LEVEL_BONUS_PERCENT": 2,
        "FLEET_BASE_GOLD_COST": SECTION_55_RULE_OVERRIDES[
            "FLEET_BASE_GOLD_COST"
        ],
        "FLEET_GOLD_COST_PER_LEVEL": SECTION_55_RULE_OVERRIDES[
            "FLEET_GOLD_COST_PER_LEVEL"
        ],
        "FLEET_BASE_WOOD_COST": SECTION_55_RULE_OVERRIDES[
            "FLEET_BASE_WOOD_COST"
        ],
        "FLEET_WOOD_COST_PER_LEVEL": SECTION_55_RULE_OVERRIDES[
            "FLEET_WOOD_COST_PER_LEVEL"
        ],
        "FLEET_WOOD_LEVEL_DIVISOR": SECTION_55_RULE_OVERRIDES[
            "FLEET_WOOD_LEVEL_DIVISOR"
        ],
        "FLEET_BASE_IRON_COST": SECTION_55_RULE_OVERRIDES[
            "FLEET_BASE_IRON_COST"
        ],
        "FLEET_IRON_COST_PER_LEVEL": SECTION_55_RULE_OVERRIDES[
            "FLEET_IRON_COST_PER_LEVEL"
        ],
        "FLEET_IRON_LEVEL_DIVISOR": SECTION_55_RULE_OVERRIDES[
            "FLEET_IRON_LEVEL_DIVISOR"
        ],
        "FLEET_BASE_FOOD_COST": SECTION_55_RULE_OVERRIDES[
            "FLEET_BASE_FOOD_COST"
        ],
        "FLEET_FOOD_LEVEL_DIVISOR": SECTION_55_RULE_OVERRIDES[
            "FLEET_FOOD_LEVEL_DIVISOR"
        ],
        "FLEET_FOOD_COST_PER_STEP": SECTION_55_RULE_OVERRIDES[
            "FLEET_FOOD_COST_PER_STEP"
        ],
        "POPULATION_BASE_GROWTH_PERCENT": 4,
        "POPULATION_GROWTH_RELIC_DIVISOR": 10,
        "POPULATION_FLAT_GROWTH_PER_LEVEL": 20,
        "POPULATION_MAXIMUM": 4_000,
        "POPULATION_INCOME_BONUS_CAP_PERCENT": 20,
        "POPULATION_PER_INCOME_PERCENT": 100,
        "POPULATION_DEVELOPMENT_BONUS_FIRST_LEVELS_PERCENT": 8,
        "POPULATION_DEVELOPMENT_BONUS_LATER_LEVELS_PERCENT": 4,
        "POPULATION_DEVELOPMENT_BONUS_BREAK_LEVEL": 5,
        "RELIC_LEVEL_1_COST_MULTIPLIER": 1,
        "RELIC_LEVEL_2_COST_MULTIPLIER": 5,
        "RELIC_LEVEL_3_COST_MULTIPLIER": 15,
        "CARAVAN_HOURS_PER_STEP": 6,
        "CARAVAN_SEA_HOURS_PER_STEP": 8,
        "CARAVAN_MIN_GOLD_FEE": 10,
        "CARAVAN_BASE_GOLD_FEE": 7,
        "CARAVAN_DISTANCE_GOLD_FEE": 4,
        "CARAVAN_VOLUME_STEP": 7,
        "CARAVAN_VOLUME_GOLD_FEE": 1,
        "CARAVAN_GOLD_FEE_MULTIPLIER_PERCENT": 100,
    },
    "rating": {
        "ELO_START_RATING": 1000,
        "ELO_PROVISIONAL_MATCHES": 30,
        "ELO_PROVISIONAL_K": 40,
        "ELO_REGULAR_K": 24,
        "ELO_EXPECTED_SCORE_DIVISOR": 400,
    },
    "clan": {
        "CLAN_ACTIVITY_WINDOW_DAYS": 28,
        "CLAN_ACTIVITY_MIN_MATCHES": 3,
        "CLAN_ATTACK_SQUAD_MIN_MEMBERS": 5,
        "CLAN_LEVEL_1_ATTACK_CAPACITY": 1,
        "CLAN_LEVEL_2_ACTIVE_MEMBERS": 11,
        "CLAN_LEVEL_2_TERRITORIES": 2,
        "CLAN_LEVEL_2_INFLUENCE": 140,
        "CLAN_LEVEL_2_ATTACK_CAPACITY": 2,
        "CLAN_LEVEL_3_ACTIVE_MEMBERS": 17,
        "CLAN_LEVEL_3_TERRITORIES": 4,
        "CLAN_LEVEL_3_INFLUENCE": 230,
        "CLAN_LEVEL_3_ATTACK_CAPACITY": 3,
        "CLAN_LEVEL_4_ACTIVE_MEMBERS": 22,
        "CLAN_LEVEL_4_TERRITORIES": 6,
        "CLAN_LEVEL_4_INFLUENCE": 340,
        "CLAN_LEVEL_4_ATTACK_CAPACITY": 4,
        "CLAN_LEVEL_5_ACTIVE_MEMBERS": 30,
        "CLAN_LEVEL_5_TERRITORIES": 10,
        "CLAN_LEVEL_5_INFLUENCE": 500,
        "CLAN_LEVEL_5_ATTACK_CAPACITY": 5,
    },
}


_STRICTLY_POSITIVE_KEYS = {
    "CLAN_ATTACK_COOLDOWN_HOURS",
    "WAR_DURATION_HOURS",
    "WAR_ELO_DRAW_DIVISOR",
    "WAR_MIN_MATCH_DURATION_SECONDS",
    "TERRITORY_RESOURCE_PAYOUT_HOURS",
    "TERRITORY_RESOURCE_READY_HOURS",
    "TERRITORY_MAX_RESOURCE_CATCHUP_CYCLES",
    "NEUTRAL_CAPTURE_REQUIRED_WINS",
    "WAR_POWER_POINTS_DIVISOR",
    "ECONOMY_TICK_HOURS",
    "ECONOMY_MAX_CATCHUP_DAYS",
    "TERRITORY_RESOURCE_WEALTH_DIVISOR",
    "TERRITORY_MIN_RESOURCE_OUTPUT",
    "TERRITORY_MAX_UPGRADE_LEVEL",
    "TERRITORY_MAX_UPGRADE_LEVELS_PER_PURCHASE",
    "OFFENSE_FOOD_LEVEL_DIVISOR",
    "POPULATION_WOOD_LEVEL_DIVISOR",
    "POPULATION_DEVELOPMENT_BONUS_BREAK_LEVEL",
    "PORT_WOOD_LEVEL_DIVISOR",
    "PORT_IRON_LEVEL_DIVISOR",
    "FLEET_WOOD_LEVEL_DIVISOR",
    "FLEET_IRON_LEVEL_DIVISOR",
    "FLEET_FOOD_LEVEL_DIVISOR",
    "POPULATION_GROWTH_RELIC_DIVISOR",
    "POPULATION_MAXIMUM",
    "POPULATION_INCOME_BONUS_CAP_PERCENT",
    "POPULATION_PER_INCOME_PERCENT",
    "RELIC_LEVEL_1_COST_MULTIPLIER",
    "RELIC_LEVEL_2_COST_MULTIPLIER",
    "RELIC_LEVEL_3_COST_MULTIPLIER",
    "CARAVAN_HOURS_PER_STEP",
    "CARAVAN_SEA_HOURS_PER_STEP",
    "CARAVAN_MIN_GOLD_FEE",
    "CARAVAN_VOLUME_STEP",
    "CARAVAN_GOLD_FEE_MULTIPLIER_PERCENT",
    "ELO_START_RATING",
    "ELO_PROVISIONAL_MATCHES",
    "ELO_PROVISIONAL_K",
    "ELO_REGULAR_K",
    "ELO_EXPECTED_SCORE_DIVISOR",
    "CLAN_ACTIVITY_WINDOW_DAYS",
    "CLAN_ACTIVITY_MIN_MATCHES",
    "CLAN_ATTACK_SQUAD_MIN_MEMBERS",
    "CLAN_LEVEL_1_ATTACK_CAPACITY",
}


def _unit_for(key: str) -> str:
    if key == "POPULATION_PER_INCOME_PERCENT":
        return "count"
    if key.endswith("_HOURS") or "HOURS_PER" in key:
        return "hours"
    if key.endswith("_DAYS"):
        return "days"
    if key.endswith("_SECONDS"):
        return "seconds"
    if key.endswith("_PERCENT"):
        return "percent"
    if "GOLD" in key:
        return "gold"
    if "WOOD" in key:
        return "wood"
    if "IRON" in key:
        return "iron"
    if "FOOD" in key:
        return "food"
    if "MITHRIL" in key:
        return "mithril"
    if key.endswith("_INFLUENCE") or "INFLUENCE_" in key:
        return "influence"
    if "MULTIPLIER" in key:
        return "multiplier"
    if "DIVISOR" in key:
        return "divisor"
    if "ELO" in key or key.endswith("_POINTS"):
        return "points"
    if key.endswith("_MEMBERS"):
        return "players"
    if key.endswith("_TERRITORIES"):
        return "territories"
    if key.endswith("_MATCHES") or key.endswith("_WINS"):
        return "matches"
    return "count"


def _bounds_for(key: str, default: RuleValue) -> tuple[RuleValue, RuleValue]:
    if key == "POPULATION_PER_INCOME_PERCENT":
        return (1, 1_000_000)
    if isinstance(default, float):
        return (0.0, 100.0)
    minimum = 1 if key in _STRICTLY_POSITIVE_KEYS else 0
    if key.endswith("_PERCENT"):
        return (minimum, 1000)
    if key.endswith("_HOURS") or "HOURS_PER" in key:
        return (minimum, 87_600)
    if key.endswith("_DAYS"):
        return (minimum, 3650)
    if key.endswith("_SECONDS"):
        return (minimum, 604_800)
    if key.endswith("_ATTACK_CAPACITY"):
        return (minimum, 100)
    return (minimum, 2_147_483_647)


def _build_rule_definitions() -> dict[str, CampaignRuleDefinition]:
    definitions: dict[str, CampaignRuleDefinition] = {}
    for category, defaults in _CATEGORY_DEFAULTS.items():
        for key, default in defaults.items():
            if key in definitions:
                raise RuntimeError(f"Duplicate campaign rule key: {key}")
            minimum, maximum = _bounds_for(key, default)
            definitions[key] = CampaignRuleDefinition(
                key=key,
                category=category,
                value_type="float" if isinstance(default, float) else "int",
                default=default,
                minimum=minimum,
                maximum=maximum,
                unit=_unit_for(key),
                label_key=f"admin_campaign_rule_{key.lower()}_label",
                help_key=f"admin_campaign_rule_{key.lower()}_help",
            )
    return definitions


RULE_DEFINITIONS = _build_rule_definitions()


def default_campaign_rule_values() -> dict[str, RuleValue]:
    return {
        key: definition.default
        for key, definition in RULE_DEFINITIONS.items()
    }


def _error(
    code: str,
    field: str | None,
    message: str,
) -> CampaignRuleValidationError:
    return CampaignRuleValidationError(code=code, field=field, message=message)


def validate_campaign_rule_values(
    values: Mapping[str, object],
) -> list[CampaignRuleValidationError]:
    """Validate a complete campaign rule set without mutating the input."""
    errors: list[CampaignRuleValidationError] = []
    expected_keys = set(RULE_DEFINITIONS)
    actual_keys = set(values)

    for key in sorted(expected_keys - actual_keys):
        errors.append(_error("missing", key, "Required campaign rule is missing."))
    for key in sorted(actual_keys - expected_keys):
        errors.append(_error("unknown", key, "Unknown campaign rule."))

    valid_values: dict[str, RuleValue] = {}
    for key in sorted(expected_keys & actual_keys):
        definition = RULE_DEFINITIONS[key]
        value = values[key]
        is_valid_type = (
            type(value) is int
            if definition.value_type == "int"
            else type(value) in {int, float}
        )
        if not is_valid_type:
            errors.append(_error("type", key, f"Expected {definition.value_type}."))
            continue
        numeric_value = value
        if key in _STRICTLY_POSITIVE_KEYS and numeric_value <= 0:
            errors.append(_error("positive_required", key, "Value must be positive."))
        if not definition.minimum <= numeric_value <= definition.maximum:
            errors.append(
                _error(
                    "bounds",
                    key,
                    f"Value must be between {definition.minimum} and {definition.maximum}.",
                )
            )
            continue
        valid_values[key] = numeric_value

    def compare_order(
        lower_key: str,
        upper_key: str,
        code: str = "range_order",
    ) -> None:
        lower = valid_values.get(lower_key)
        upper = valid_values.get(upper_key)
        if lower is not None and upper is not None and lower > upper:
            errors.append(
                _error(code, lower_key, f"{lower_key} must not exceed {upper_key}.")
            )

    compare_order("WAR_ELO_MIN_POINTS", "WAR_ELO_BASE_POINTS")
    compare_order("WAR_ELO_BASE_POINTS", "WAR_ELO_MAX_POINTS")
    compare_order("WAR_ELO_MIN_DRAW_POINTS", "WAR_ELO_MAX_DRAW_POINTS")
    compare_order("ELO_REGULAR_K", "ELO_PROVISIONAL_K")
    compare_order(
        "TERRITORY_MAX_UPGRADE_LEVELS_PER_PURCHASE",
        "TERRITORY_MAX_UPGRADE_LEVEL",
    )
    compare_order("RELIC_LEVEL_1_COST_MULTIPLIER", "RELIC_LEVEL_2_COST_MULTIPLIER")
    compare_order("RELIC_LEVEL_2_COST_MULTIPLIER", "RELIC_LEVEL_3_COST_MULTIPLIER")

    for key in sorted(_STRICTLY_POSITIVE_KEYS):
        if key in valid_values and valid_values[key] <= 0:
            errors.append(_error("positive_required", key, "Value must be positive."))

    level_dimensions = (
        "ACTIVE_MEMBERS",
        "TERRITORIES",
        "INFLUENCE",
        "ATTACK_CAPACITY",
    )
    for dimension in level_dimensions:
        start_level = 1 if dimension == "ATTACK_CAPACITY" else 2
        for level in range(start_level + 1, 6):
            previous_key = f"CLAN_LEVEL_{level - 1}_{dimension}"
            current_key = f"CLAN_LEVEL_{level}_{dimension}"
            previous = valid_values.get(previous_key)
            current = valid_values.get(current_key)
            if previous is not None and current is not None and current < previous:
                errors.append(
                    _error(
                        "level_order",
                        current_key,
                        f"{current_key} must not be lower than {previous_key}.",
                    )
                )

    return errors
