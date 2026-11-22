from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from app.core.campaign_rules import default_campaign_rule_values
from app.core.section_55_balance import (
    SECTION_55_BALANCE_VERSION,
    SECTION_55_RELIC_COSTS,
    SECTION_55_RULE_OVERRIDES,
)
from app.models.campaign import CampaignRuleSet
from app.models.clan_asset import ClanAsset
from app.models.territory import Territory
from app.services.section_55_balance_service import build_section_55_balance_report


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "w9l0m1n2o3p4_complete_section_55_economy.py"
)


def _migration_module():
    spec = spec_from_file_location("section_55_economy_migration", MIGRATION_PATH)
    module = module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_section_55_acceptance_report_covers_every_requirement():
    report = build_section_55_balance_report()

    assert report["balance_version"] == SECTION_55_BALANCE_VERSION
    assert report["passed"] is True
    assert report["map"]["ordinary_count"] == 65
    assert report["map"]["stronghold_count"] == 10
    assert report["map"]["ordinary_gold"] == {
        "min": 40,
        "max": 60,
        "average": 50.385,
    }
    assert report["map"]["stronghold_gold"] == {
        "min": 140,
        "max": 160,
        "average": 148,
        "ratio": 2.937,
    }
    assert report["relics"]["average_saving_days"] == 8.72
    assert {
        row["type"]: row["worst_saving_days"] for row in report["upgrades"]
    } == {
        "population": 10.42,
        "fortifications": 8.93,
        "offense": 8.93,
        "naval": 8.93,
    }
    assert report["trade"]["daily_income_share_percent"] == {
        "near_10_units": 5.16,
        "far_50_units": 18.66,
    }
    assert all(check["passed"] for check in report["checks"])


def test_section_55_migration_is_a_snapshot_of_the_approved_balance():
    migration = _migration_module()

    assert migration.down_revision == "v8k9l0m1n2o3"
    assert migration.RULE_SET_REASON == SECTION_55_BALANCE_VERSION
    assert migration.RULE_OVERRIDES == SECTION_55_RULE_OVERRIDES
    assert migration.RELIC_COSTS == SECTION_55_RELIC_COSTS


def test_section_55_migration_updates_and_safely_restores_data(db):
    migration = _migration_module()
    previous_rules = default_campaign_rule_values()
    previous_rules.update(
        {
            "POPULATION_BASE_GOLD_COST": 140,
            "FORTIFICATION_BASE_GOLD_COST": 280,
        }
    )
    db.add(
        CampaignRuleSet(
            version=7,
            values=previous_rules,
            is_active=True,
            reason="economy_v4_fast_lore_season",
        )
    )
    ordinary = Territory(
        name="Эвендим",
        region="eriador",
        svg_path_data="M0 0",
        resource_type="food",
        resource_output=1,
        resource_wealth=45,
        influence_value=30,
        required_influence=60,
    )
    stronghold = Territory(
        name="Минас Тирит",
        region="gondor",
        svg_path_data="M1 1",
        resource_type="iron",
        resource_output=1,
        secondary_resource_type="food",
        resource_wealth=220,
        influence_value=160,
        required_influence=500,
        required_territories=8,
        stronghold_power=5,
    )
    relic = ClanAsset(
        key="iron_crown",
        name="Железная корона",
        bonus_type="defense_power",
        gold_cost=1109,
        iron_cost=4,
        food_cost=1,
    )
    db.add_all([ordinary, stronghold, relic])
    db.flush()

    bind = db.connection()
    migration._activate_rules(bind)
    migration._apply_territory_balance(bind)
    migration._apply_relic_costs(bind, migration.RELIC_COSTS)
    db.expire_all()

    active = db.query(CampaignRuleSet).filter_by(is_active=True).one()
    assert active.version == 8
    assert active.reason == SECTION_55_BALANCE_VERSION
    assert active.values["POPULATION_BASE_GOLD_COST"] == 100
    assert active.values["FORTIFICATION_BASE_GOLD_COST"] == 100
    assert (ordinary.resource_wealth, ordinary.influence_value) == (45, 50)
    assert (
        stronghold.resource_wealth,
        stronghold.required_influence,
        stronghold.required_territories,
    ) == (160, 350, 5)
    assert (relic.gold_cost, relic.iron_cost) == (1900, 5)

    migration._restore_previous_relic_costs(bind)
    migration._restore_previous_territory_balance(bind)
    migration._restore_previous_rules(bind)
    db.expire_all()

    restored = db.query(CampaignRuleSet).filter_by(is_active=True).one()
    assert restored.version == 7
    assert (
        ordinary.resource_wealth,
        ordinary.influence_value,
        ordinary.required_influence,
    ) == (45, 30, 60)
    assert (
        stronghold.resource_wealth,
        stronghold.required_influence,
        stronghold.required_territories,
    ) == (220, 500, 8)
    assert (relic.gold_cost, relic.iron_cost) == (1109, 4)
