from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "k7f8a9b0c1d2_rebalance_economy_v3.py"
)


def _migration_module():
    assert MIGRATION_PATH.exists(), "Миграция экономики v3 ещё не создана"
    spec = spec_from_file_location("economy_v3_migration", MIGRATION_PATH)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_economy_v3_migration_contains_the_approved_rule_overrides():
    migration = _migration_module()

    assert migration.down_revision == "j6e7f8a9b0c1"
    assert migration.RULE_OVERRIDES["POPULATION_BASE_GOLD_COST"] == 150
    assert migration.RULE_OVERRIDES["PORT_BASE_GOLD_COST"] == 320
    assert migration.RULE_OVERRIDES["FLEET_BASE_GOLD_COST"] == 380
    assert migration.RULE_OVERRIDES["CARAVAN_GOLD_FEE_MULTIPLIER_PERCENT"] == 120


def test_economy_v3_migration_discounts_standard_relics_by_twelve_percent():
    migration = _migration_module()

    assert migration._discounted_cost(1260) == 1109
    assert migration._discounted_cost(1680) == 1478
    assert migration._discounted_cost(2100) == 1848
    assert migration._discounted_cost(1) == 1
    assert len(migration.RELIC_BALANCE) == 15
