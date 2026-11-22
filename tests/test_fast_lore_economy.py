from collections import Counter
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from app.core.campaign_rules import default_campaign_rule_values
from app.core.territory_resource_balance import (
    RESOURCE_TYPES,
    TERRITORY_BALANCE,
)
from app.models.campaign import CampaignRuleSet
from app.models.clan import Clan
from app.models.territory import Territory
from app.services.bootstrap_service import STRONGHOLD_RULES


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "u7j8k9l0m1n2_activate_fast_lore_economy.py"
)


def _migration_module():
    spec = spec_from_file_location("fast_lore_economy_migration", MIGRATION_PATH)
    module = module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_lore_balance_covers_the_complete_playable_map():
    assert len(TERRITORY_BALANCE) == 75
    assert all(item.resource_type in RESOURCE_TYPES for item in TERRITORY_BALANCE.values())
    assert all(item.resource_output in {1, 2} for item in TERRITORY_BALANCE.values())
    assert sum(item.stronghold_power > 0 for item in TERRITORY_BALANCE.values()) == 10


def test_lore_balance_keeps_mithril_at_the_moria_lode():
    mithril_names = {
        name
        for name, item in TERRITORY_BALANCE.items()
        if item.resource_type == "mithril"
    }
    assert mithril_names == {"Врата Мории", "Перевал Карадрас"}
    assert TERRITORY_BALANCE["Железные холмы"].resource_type == "iron"
    assert TERRITORY_BALANCE["Шир"].resource_type == "food"
    assert TERRITORY_BALANCE["Фангорн"].resource_type == "wood"
    assert TERRITORY_BALANCE["Море Нурнен"].resource_type == "food"


def test_bootstrap_uses_the_same_stronghold_rules_as_the_lore_map():
    expected = {
        name: (item.required_territories, item.stronghold_power)
        for name, item in TERRITORY_BALANCE.items()
        if item.stronghold_power > 0
    }
    assert STRONGHOLD_RULES == expected


def test_resource_distribution_supports_trade_without_a_single_common_monopoly():
    counts = Counter(item.resource_type for item in TERRITORY_BALANCE.values())
    output = {
        resource: sum(
            item.resource_output
            for item in TERRITORY_BALANCE.values()
            if item.resource_type == resource
        )
        for resource in RESOURCE_TYPES
    }

    assert counts == {"food": 31, "iron": 26, "wood": 16, "mithril": 2}
    assert output == {"food": 37, "iron": 33, "wood": 23, "mithril": 3}


def test_fast_lore_migration_activates_the_approved_variant_b_values():
    migration = _migration_module()

    assert migration.down_revision == "t6i7j8k9l0m1"
    assert migration.RULE_SET_REASON == "economy_v4_fast_lore_season"
    assert migration.RULE_OVERRIDES == {
        "CAMPAIGN_STARTING_GOLD": 100,
        "CAMPAIGN_STARTING_IRON": 6,
        "CAMPAIGN_STARTING_WOOD": 6,
        "CAMPAIGN_STARTING_FOOD": 3,
        "CAMPAIGN_STARTING_MITHRIL": 0,
        "POPULATION_BASE_GOLD_COST": 140,
        "POPULATION_GOLD_COST_PER_LEVEL": 60,
        "POPULATION_DEVELOPMENT_BONUS_FIRST_LEVELS_PERCENT": 8,
        "POPULATION_DEVELOPMENT_BONUS_LATER_LEVELS_PERCENT": 4,
        "FORTIFICATION_BASE_GOLD_COST": 280,
        "FORTIFICATION_GOLD_COST_PER_LEVEL": 140,
        "FORTIFICATION_BASE_IRON_COST": 2,
        "OFFENSE_BASE_GOLD_COST": 300,
        "OFFENSE_GOLD_COST_PER_LEVEL": 150,
        "OFFENSE_BASE_IRON_COST": 2,
        "PORT_BASE_GOLD_COST": 260,
        "PORT_GOLD_COST_PER_LEVEL": 110,
        "PORT_BASE_IRON_COST": 1,
        "FLEET_BASE_GOLD_COST": 320,
        "FLEET_GOLD_COST_PER_LEVEL": 130,
        "FLEET_BASE_WOOD_COST": 3,
        "CARAVAN_GOLD_FEE_MULTIPLIER_PERCENT": 100,
    }


def test_fast_lore_migration_updates_map_and_only_untouched_treasuries(db):
    migration = _migration_module()
    previous_values = default_campaign_rule_values()
    previous_values.update(
        {
            "POPULATION_BASE_GOLD_COST": 150,
            "CAMPAIGN_STARTING_GOLD": 500,
        }
    )
    db.add(
        CampaignRuleSet(
            version=5,
            values=previous_values,
            is_active=True,
            reason="economy_v3_population_naval_market_relics",
        )
    )
    untouched = Clan(
        name="Untouched",
        gold=500,
        iron=10,
        wood=10,
        food=5,
        mithril=2,
    )
    active = Clan(
        name="Active",
        gold=500,
        iron=10,
        wood=10,
        food=5,
        mithril=2,
    )
    iron_hills = Territory(
        name="Железные холмы",
        region="rhovanion",
        svg_path_data="M0 0",
        resource_type="wood",
        resource_output=1,
    )
    shire = Territory(
        name="Шир",
        region="eriador",
        svg_path_data="M1 1",
        resource_type="wood",
        resource_output=1,
        owner_clan=active,
    )
    db.add_all([untouched, active, iron_hills, shire])
    db.flush()

    bind = db.connection()
    migration._activate_rules(bind)
    migration._normalize_territories(bind)
    migration._migrate_untouched_clan_treasuries(bind)
    db.expire_all()

    activated = db.query(CampaignRuleSet).filter_by(is_active=True).one()
    assert activated.version == 6
    assert activated.reason == migration.RULE_SET_REASON
    assert activated.values["POPULATION_BASE_GOLD_COST"] == 140
    assert activated.values["CAMPAIGN_STARTING_GOLD"] == 100
    assert (
        untouched.gold,
        untouched.iron,
        untouched.wood,
        untouched.food,
        untouched.mithril,
    ) == (100, 6, 6, 3, 0)
    assert (active.gold, active.iron, active.wood, active.food, active.mithril) == (
        500,
        10,
        10,
        5,
        2,
    )
    assert iron_hills.resource_type == "iron"
    assert iron_hills.resource_output == 2
    assert shire.resource_type == "food"
    assert shire.resource_output == 2
