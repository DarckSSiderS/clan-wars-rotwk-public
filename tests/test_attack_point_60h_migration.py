from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa

from app.core.campaign_rules import default_campaign_rule_values
from app.core.time import as_utc
from app.models.campaign import CampaignRuleSet, CampaignSeason, CampaignSettings
from app.models.clan import Clan
from app.models.clan_warfare import ClanAttackPointSpend
from app.models.territory import Territory
from app.models.war import ClanWar
from app.services.clan_attack_point_service import ClanAttackPointService


NOW = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)


def _migration(db, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/a3p4q5r6s7t8_attack_point_60_hours.py"
    spec = spec_from_file_location("attack_point_60h_migration", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(db.connection())))
    monkeypatch.setattr(module, "_effective_now", lambda bind: NOW)
    return module


@pytest.mark.parametrize("database", ["db", "postgres_db"])
def test_migration_recovers_overdue_points_and_preserves_other_campaign_data(request, monkeypatch, database):
    db = request.getfixturevalue(database)
    values = {**default_campaign_rule_values(), "CLAN_ATTACK_COOLDOWN_HOURS": 96, "WAR_ELO_BASE_POINTS": 12}
    rules = CampaignRuleSet(version=8, values=values, is_active=True, reason="existing")
    custom = CampaignRuleSet(version=9, values={**values, "CLAN_ATTACK_COOLDOWN_HOURS": 84}, is_active=False, reason="custom")
    clan = Clan(name="Recovery clan", level=3, gold=1234, territory_points=234)
    db.add_all([rules, custom, clan])
    db.flush()
    land = Territory(name="Preserved", region="Test", svg_path_data="M0 0", owner_clan_id=clan.id)
    db.add(land)
    db.flush()
    war = ClanWar(territory_id=land.id, attacking_clan_id=clan.id, war_type="neutral_capture",
                  status="active", started_at=NOW - timedelta(hours=24), ends_at=NOW + timedelta(hours=36),
                  campaign_rule_set_id=rules.id, rules_snapshot=values)
    season = CampaignSeason(number=1, name="Season", status="active", starts_at=NOW - timedelta(days=10),
                            starting_influence=100, reset_development=False, rules_snapshot={"values": values})
    db.add_all([war, season])
    rows = []
    for age, duration, refunded, selected in [
        (72, 96, False, rules), (24, 96, False, rules), (23, 96, False, rules),
        (120, 96, False, rules), (24, 96, True, rules), (24, 104, False, rules),
        (24, 84, False, custom),
    ]:
        spent = NOW - timedelta(hours=age)
        row = ClanAttackPointSpend(clan_id=clan.id, origin="legacy_next_attack_at", spent_at=spent,
                                   recover_at=spent + timedelta(hours=duration), level_snapshot=3,
                                   capacity_snapshot=3, campaign_rule_set_id=selected.id, rule_version=selected.version,
                                   refunded_at=NOW if refunded else None)
        db.add(row)
        rows.append(row)
    db.flush()
    original = [as_utc(row.recover_at) for row in rows]
    module = _migration(db, monkeypatch)
    module.upgrade()
    db.expire_all()
    active = db.query(CampaignRuleSet).filter_by(is_active=True).one()
    assert active.version == 10
    assert active.values == {**values, "CLAN_ATTACK_COOLDOWN_HOURS": 60}
    assert rules.values == values and rules.is_active is False
    expected = [value - timedelta(hours=36) if index in (0, 1, 2, 5) else value for index, value in enumerate(original)]
    assert [as_utc(row.recover_at) for row in rows] == expected
    assert [row.rule_version for row in rows] == [8, 8, 8, 8, 8, 8, 9]
    assert as_utc(war.ends_at) == NOW + timedelta(hours=36)
    assert war.rules_snapshot == values and season.rules_snapshot == {"values": values}
    assert (clan.gold, clan.territory_points, land.owner_clan_id) == (1234, 234, clan.id)
    assert as_utc(clan.next_attack_at) == NOW + timedelta(hours=36)
    assert db.execute(sa.text(f"SELECT count(*) FROM {module.BACKUP_TABLE}")).scalar_one() == 4
    module._migrate_pending(db.connection(), NOW)
    db.expire_all()
    assert [as_utc(row.recover_at) for row in rows] == expected
    status = ClanAttackPointService().status(db, clan, capacity=5, now=NOW)
    assert status.available == 1 and status.recovering == 4
    module.downgrade()
    db.expire_all()
    assert [as_utc(row.recover_at) for row in rows] == original
    restored = db.query(CampaignRuleSet).filter_by(is_active=True).one()
    assert restored.version == 11 and restored.values == values
    assert not sa.inspect(db.connection()).has_table(module.BACKUP_TABLE)
    # Upgrade/downgrade keep referenced history; a subsequent upgrade remains safe.
    module.upgrade()
    db.expire_all()
    assert db.query(CampaignRuleSet).filter_by(is_active=True).one().values["CLAN_ATTACK_COOLDOWN_HOURS"] == 60
    assert [as_utc(row.recover_at) for row in rows] == expected
    module.downgrade()


def test_migration_uses_campaign_pause_time(db, monkeypatch):
    module = _migration(db, monkeypatch)
    monkeypatch.undo()
    db.add(CampaignSettings(id=1, is_paused=True, paused_at=NOW))
    db.flush()
    assert module._effective_now(db.connection()) == NOW
