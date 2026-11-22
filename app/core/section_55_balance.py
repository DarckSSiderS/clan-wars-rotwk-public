from __future__ import annotations


SECTION_55_BALANCE_VERSION = "economy_v5_section_55"

ACTIVE_CLAN_TERRITORIES = 5
ACTIVE_CLAN_STARTING_GOLD = 100
ACTIVE_CLAN_STARTING_INFLUENCE = 100
TARGET_MIN_DAYS = 7.0
TARGET_MAX_DAYS = 10.5

ORDINARY_GOLD_CENTER = 50
ORDINARY_GOLD_TOLERANCE = 10
STRONGHOLD_GOLD_CENTER = 150
STRONGHOLD_GOLD_TOLERANCE = 10
STRONGHOLD_MIN_GOLD_RATIO = 2.8
STRONGHOLD_MAX_GOLD_RATIO = 3.2

ORDINARY_INFLUENCE = 50
STRONGHOLD_REQUIRED_TERRITORIES = 5
STRONGHOLD_REQUIRED_INFLUENCE = 350


# gold/day, influence from ownership, influence required to attack
ORDINARY_TIER_BALANCE = {
    "frontier": (40, ORDINARY_INFLUENCE, 30),
    "standard": (45, ORDINARY_INFLUENCE, 60),
    "valuable": (55, ORDINARY_INFLUENCE, 90),
    "hub": (60, ORDINARY_INFLUENCE, 120),
}


# gold/day, influence from ownership, influence required to attack,
# required territories, stronghold power
STRONGHOLD_TIER_BALANCE = {
    "minor": (
        140,
        90,
        STRONGHOLD_REQUIRED_INFLUENCE,
        STRONGHOLD_REQUIRED_TERRITORIES,
        3,
    ),
    "major": (
        150,
        120,
        STRONGHOLD_REQUIRED_INFLUENCE,
        STRONGHOLD_REQUIRED_TERRITORIES,
        4,
    ),
    "capital": (
        160,
        160,
        STRONGHOLD_REQUIRED_INFLUENCE,
        STRONGHOLD_REQUIRED_TERRITORIES,
        5,
    ),
}


SECTION_55_RULE_OVERRIDES = {
    "POPULATION_BASE_GOLD_COST": 100,
    "POPULATION_GOLD_COST_PER_LEVEL": 25,
    "POPULATION_GOLD_COST_WEALTH_PERCENT": 100,
    "POPULATION_BASE_WOOD_COST": 1,
    "POPULATION_WOOD_COST_PER_LEVEL": 0,
    "FORTIFICATION_BASE_GOLD_COST": 100,
    "FORTIFICATION_GOLD_COST_PER_LEVEL": 30,
    "FORTIFICATION_BASE_IRON_COST": 1,
    "FORTIFICATION_IRON_COST_PER_LEVEL": 0,
    "FORTIFICATION_MITHRIL_START_LEVEL": 10,
    "OFFENSE_BASE_GOLD_COST": 100,
    "OFFENSE_GOLD_COST_PER_LEVEL": 30,
    "OFFENSE_BASE_IRON_COST": 1,
    "OFFENSE_IRON_COST_PER_LEVEL": 0,
    "OFFENSE_BASE_FOOD_COST": 0,
    "OFFENSE_FOOD_LEVEL_DIVISOR": 5,
    "OFFENSE_FOOD_COST_PER_STEP": 1,
    "PORT_BASE_GOLD_COST": 50,
    "PORT_GOLD_COST_PER_LEVEL": 15,
    "PORT_BASE_WOOD_COST": 0,
    "PORT_WOOD_COST_PER_LEVEL": 1,
    "PORT_WOOD_LEVEL_DIVISOR": 5,
    "PORT_BASE_IRON_COST": 0,
    "PORT_IRON_LEVEL_DIVISOR": 5,
    "PORT_IRON_COST_PER_STEP": 1,
    "FLEET_BASE_GOLD_COST": 50,
    "FLEET_GOLD_COST_PER_LEVEL": 15,
    "FLEET_BASE_WOOD_COST": 0,
    "FLEET_WOOD_COST_PER_LEVEL": 1,
    "FLEET_WOOD_LEVEL_DIVISOR": 5,
    "FLEET_BASE_IRON_COST": 0,
    "FLEET_IRON_COST_PER_LEVEL": 1,
    "FLEET_IRON_LEVEL_DIVISOR": 5,
    "FLEET_BASE_FOOD_COST": 0,
    "FLEET_FOOD_LEVEL_DIVISOR": 5,
    "FLEET_FOOD_COST_PER_STEP": 1,
}


# Final level-one prices. The remaining tuple values are iron, wood, food,
# and mithril. Higher levels still use the versioned 1x/5x/15x multipliers.
SECTION_55_RELIC_COSTS = {
    "royal_charter": (1900, 3, 3, 0, 0),
    "red_arrow": (1900, 2, 4, 1, 0),
    "iron_crown": (1900, 5, 0, 1, 0),
    "war_foundry": (2250, 5, 0, 3, 2),
    "merchant_guild": (2250, 0, 6, 3, 2),
    "white_tree": (2250, 0, 5, 2, 2),
    "dwarf_anvil": (2250, 6, 0, 1, 2),
    "ents_seed": (2250, 0, 7, 2, 1),
    "mordor_forge": (2250, 4, 0, 4, 2),
    "helms_horn": (2250, 5, 3, 0, 2),
    "mithril_standard": (2600, 4, 2, 2, 4),
    "granite_bastion": (2600, 6, 1, 0, 4),
    "palantir": (2600, 2, 2, 4, 3),
    "ring_of_barahir": (2600, 2, 1, 4, 4),
    "galadhrim_mirror": (2600, 0, 5, 3, 4),
}


RELIC_COST_FIELDS = (
    "gold_cost",
    "iron_cost",
    "wood_cost",
    "food_cost",
    "mithril_cost",
)


def relic_cost_fields(key: str) -> dict[str, int]:
    return dict(zip(RELIC_COST_FIELDS, SECTION_55_RELIC_COSTS[key], strict=True))
