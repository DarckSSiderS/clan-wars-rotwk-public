import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.campaign_rules import default_campaign_rule_values
from app.models.campaign import CampaignRuleSet


def test_campaign_rule_set_stores_full_version(db):
    row = CampaignRuleSet(
        version=1,
        values=default_campaign_rule_values(),
        is_active=True,
        reason="test_defaults",
    )
    db.add(row)
    db.commit()

    stored = db.query(CampaignRuleSet).one()
    assert stored.values["CLAN_ACTIVITY_WINDOW_DAYS"] == 28
    assert stored.reason == "test_defaults"
    assert stored.created_at is not None


def test_only_one_campaign_rule_set_can_be_active(db):
    db.add_all(
        [
            CampaignRuleSet(
                version=1,
                values=default_campaign_rule_values(),
                is_active=True,
                reason="first",
            ),
            CampaignRuleSet(
                version=2,
                values=default_campaign_rule_values(),
                is_active=True,
                reason="second",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db.commit()


def test_migrations_keep_v1_history_and_activate_current_v2_defaults():
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "b8c9d0e1f2a3_add_campaign_rule_sets.py"
    )
    spec = importlib.util.spec_from_file_location("campaign_rule_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.INITIAL_CAMPAIGN_RULE_VALUES["TERRITORY_RESOURCE_PAYOUT_HOURS"] == 168
    assert default_campaign_rule_values()["TERRITORY_RESOURCE_PAYOUT_HOURS"] == 24

    v2_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "e1f2a3b4c5d6_add_economy_v2.py"
    )
    v2_spec = importlib.util.spec_from_file_location("economy_v2_migration", v2_path)
    assert v2_spec is not None and v2_spec.loader is not None
    v2_migration = importlib.util.module_from_spec(v2_spec)
    v2_spec.loader.exec_module(v2_migration)
    assert v2_migration.default_campaign_rule_values() == default_campaign_rule_values()


def test_economy_v2_rule_merge_preserves_non_economy_admin_settings():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "e1f2a3b4c5d6_add_economy_v2.py"
    )
    spec = importlib.util.spec_from_file_location("economy_v2_rule_merge", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    merged = migration._merge_economy_v2_rules({
        "WAR_DURATION_HOURS": 99,
        "TERRITORY_RESOURCE_PAYOUT_HOURS": 168,
        "TERRITORY_MAX_WEEKLY_CATCHUP_CYCLES": 8,
    })

    assert merged["WAR_DURATION_HOURS"] == 99
    assert merged["TERRITORY_RESOURCE_PAYOUT_HOURS"] == 24
    assert merged["TERRITORY_RESOURCE_READY_HOURS"] == 48
    assert "TERRITORY_MAX_WEEKLY_CATCHUP_CYCLES" not in merged


def test_population_scale_migration_changes_only_population_rules():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "f2a3b4c5d6e7_rebalance_population_scale.py"
    )
    assert migration_path.exists()

    spec = importlib.util.spec_from_file_location("population_scale_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    merged = migration._merge_population_rules({
        "WAR_DURATION_HOURS": 72,
        "POPULATION_BASE_GROWTH_PERCENT": 9,
        "POPULATION_MAXIMUM": 999_999,
    })

    assert merged["WAR_DURATION_HOURS"] == 72
    assert merged["POPULATION_BASE_GROWTH_PERCENT"] == 4
    assert merged["POPULATION_FLAT_GROWTH_PER_LEVEL"] == 20
    assert merged["POPULATION_MAXIMUM"] == 4_000
    assert merged["POPULATION_INCOME_BONUS_CAP_PERCENT"] == 20
    assert merged["POPULATION_PER_INCOME_PERCENT"] == 100
