from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from app.core.campaign_rules import default_campaign_rule_values
from app.core.territory_development import (
    MILITARY_TERRITORIES, SETTLED_TERRITORIES, initial_military_level,
)
from app.core.territory_resource_balance import TERRITORY_BALANCE
from app.core.time import as_utc
from app.models.campaign import CampaignRuleSet, CampaignSeason
from app.models.clan import Clan
from app.models.territory import Territory, TerritoryOwnershipHistory
from app.models.war import ClanWar
from app.services.clan_economy_service import ClanEconomyService
from app.services.bootstrap_service import ensure_campaign_rules
from app.services.territory_adjacency_service import ensure_svg_territories


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)


def migration():
    path = ROOT / "alembic/versions/y1n2o3p4q5r6_campaign_requirements_79_80.py"
    spec = spec_from_file_location("requirements_migration", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_preserves_campaign_and_only_updates_untouched_neutral_lands(db, monkeypatch):
    values = default_campaign_rule_values()
    values.update(WAR_DURATION_HOURS=96, CLAN_ATTACK_COOLDOWN_HOURS=84, WAR_ELO_BASE_POINTS=12)
    rules = CampaignRuleSet(version=7, values=values, is_active=True, reason="custom")
    clan = Clan(name="Existing clan", gold=789, territory_points=333)
    db.add_all([rules, clan])
    db.flush()
    lands = []
    for name in ["Шир", "Дейл", "Форност", "Минас Тирит", "Owned", "Contested",
                 "Developed", "Formerly owned", "Тол-Фалас", "Coast", "Hidden"]:
        land = Territory(name=name, region="test", svg_path_data="M0 0", status="neutral")
        db.add(land)
        lands.append(land)
    db.flush()
    lands[4].owner_clan_id = clan.id
    lands[6].offense_level = 6
    lands[9].has_port = True
    lands[10].is_playable = False
    db.add(TerritoryOwnershipHistory(
        territory_id=lands[7].id, clan_id=clan.id, started_at=NOW - timedelta(days=10),
        ended_at=NOW, reason="capture",
    ))
    war = ClanWar(
        territory_id=lands[5].id, attacking_clan_id=clan.id, war_type="neutral_capture",
        status="active", started_at=NOW, ends_at=NOW + timedelta(hours=96),
        campaign_rule_set_id=rules.id, rules_snapshot=values,
    )
    season = CampaignSeason(
        number=1, name="Test season", status="active", starts_at=NOW - timedelta(days=6),
        starting_influence=100, reset_development=False,
        rules_snapshot={"version": 7, "values": values},
    )
    db.add_all([war, season])
    db.flush()
    module = migration()
    monkeypatch.setattr(module.op, "get_bind", db.connection)
    module.upgrade()
    db.expire_all()
    active = db.query(CampaignRuleSet).filter_by(is_active=True).one()
    assert active.version == 8
    assert active.values == {**values, "WAR_DURATION_HOURS": 60}
    assert rules.values == values
    assert rules.is_active is False
    assert war.rules_snapshot == values
    assert as_utc(war.ends_at) == NOW + timedelta(hours=96)
    assert season.rules_snapshot == {"version": 7, "values": values}
    assert clan.gold == 789 and clan.territory_points == 333
    assert [land.offense_level for land in lands] == [1, 2, 3, 4, 0, 0, 6, 0, 0, 1, 0]
    assert [land.fortifications for land in lands] == [1, 2, 3, 4, 0, 0, 0, 0, 0, 1, 0]
    assert lands[9].strategic_value == 0.5
    module.upgrade()
    assert db.query(CampaignRuleSet).count() == 2
    module.downgrade()
    db.expire_all()
    restored = db.query(CampaignRuleSet).filter_by(is_active=True).one()
    assert restored.version == 9 and restored.values == values
    assert db.query(CampaignRuleSet).count() == 3
    assert lands[3].fortifications == 4


def test_svg_bootstrap_assigns_all_lore_tiers_without_reapplying_losses(db):
    assert SETTLED_TERRITORIES | MILITARY_TERRITORIES <= TERRITORY_BALANCE.keys()
    assert not SETTLED_TERRITORIES & MILITARY_TERRITORIES
    path = ROOT / "frontend/public/map-interactive.svg"
    ensure_campaign_rules(db)
    assert db.query(Territory).count() == 76
    for land in db.query(Territory).all():
        expected = initial_military_level(land.name)
        assert land.offense_level == land.fortifications == expected
        assert land.strategic_value == land.calculate_strategic_value()
    fortress = db.query(Territory).filter_by(name="Минас Тирит").one()
    assert fortress.offense_level == 4
    fortress.offense_level = fortress.fortifications = 0
    db.commit()
    ensure_svg_territories(db, path)
    assert fortress.offense_level == fortress.fortifications == 0


@pytest.mark.parametrize("reset", [True, False])
def test_season_reset_uses_initial_levels_only_when_requested(db, reset):
    land = Territory(
        name="Минас Тирит", region="test", svg_path_data="M0 0", stronghold_power=5,
        offense_level=8, fortifications=6, development_level=3, port_level=2, fleet_level=2,
    )
    db.add(land)
    db.commit()
    ClanEconomyService().start_new_season(db, starting_influence=100, reset_development=reset)
    assert (land.offense_level, land.fortifications, land.development_level) == (
        (4, 4, 0) if reset else (8, 6, 3)
    )
