from datetime import datetime, timedelta, timezone

import pytest

from app.models.clan import Clan
from app.models.operation import ResourceLedgerEntry
from app.models.territory import Territory, TerritoryOwnershipHistory
from app.core.time import as_utc
from app.services.clan_economy_service import ClanEconomyService
from app.services.war_service import get_attack_influence_cost
from app.schemas.territory import TerritoryUpdate
from app.repositories.territory_repository import TerritoryRepository
from app.services.territory_ownership_service import TerritoryOwnershipService


def add_clan(db, name: str):
    clan = Clan(
        name=name,
        base_influence=100,
        territory_points=100,
        gold=100,
        resources=100,
        iron=0,
        wood=0,
        food=0,
        mithril=0,
    )
    db.add(clan)
    db.commit()
    return clan


def add_territory(db, name: str, **values):
    territory_values = {
        "resource_type": "mithril",
        "resource_output": 2,
        "resource_wealth": 20,
        "influence_value": 40,
        "strategic_value": 2,
        "population": 10000,
    }
    territory_values.update(values)
    territory = Territory(
        name=name,
        region="gondor",
        svg_path_data=f"M 0 0 L {len(name) + 2} 0 L 1 1 Z",
        **territory_values,
    )
    db.add(territory)
    db.commit()
    return territory


@pytest.mark.parametrize("level", range(11))
def test_conquest_halves_development_once_and_records_loss(db, level):
    first = add_clan(db, "Original owner")
    second = add_clan(db, "Conqueror")
    fields = ("offense_level", "fortifications", "development_level", "port_level", "fleet_level")
    territory = add_territory(
        db, "Developed coast", owner_clan_id=first.id, has_port=True,
        **{field: level for field in fields},
    )
    service = TerritoryOwnershipService()
    service.transfer(db, territory, second.id, reason="war_victory")
    db.commit()
    assert {field: getattr(territory, field) for field in fields} == {
        field: level // 2 for field in fields
    }
    assert territory.population == 10000
    assert territory.has_port is True
    assert territory.strategic_value == level // 2
    entry = db.query(ResourceLedgerEntry).filter_by(action="territory_influence_gained").one()
    assert entry.details["development_before"]["offense_level"] == level
    assert entry.details["development_after"]["offense_level"] == level // 2
    assert not service.transfer(db, territory, second.id, reason="war_victory")
    assert territory.offense_level == level // 2


@pytest.mark.parametrize("case", ["neutral", "defense", "admin", "release"])
def test_non_conquest_transfers_preserve_development(db, case):
    first = add_clan(db, "Defender")
    second = add_clan(db, "Other clan")
    territory = add_territory(
        db, "Preserved land", owner_clan_id=None if case == "neutral" else first.id,
        offense_level=6, fortifications=8, development_level=5, port_level=3, fleet_level=3,
    )
    new_owner = None if case == "release" else first.id if case == "defense" else second.id
    TerritoryOwnershipService().transfer(
        db, territory, new_owner,
        reason="admin_assignment" if case == "admin" else "war_victory",
    )
    assert (territory.offense_level, territory.fortifications, territory.development_level,
            territory.port_level, territory.fleet_level) == (6, 8, 5, 3, 3)


def test_transfer_records_history_and_resets_resource_clock(db):
    first = add_clan(db, "Первый владелец")
    second = add_clan(db, "Второй владелец")
    territory = add_territory(db, "Историческая земля")
    service = TerritoryOwnershipService()
    captured_at = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
    changed_at = captured_at + timedelta(days=10)

    assert service.transfer(
        db,
        territory,
        first.id,
        changed_at=captured_at,
        reason="test_capture",
    )
    db.commit()
    assert as_utc(territory.owned_since) == captured_at
    assert as_utc(territory.resource_income_ready_at) == captured_at + timedelta(hours=48)
    assert territory.last_resource_payout_at is None
    assert first.territory_points == 140
    assert second.territory_points == 100

    assert not service.transfer(
        db,
        territory,
        first.id,
        changed_at=captured_at + timedelta(days=3),
        reason="repeat_bootstrap",
    )
    assert as_utc(territory.owned_since) == captured_at

    assert service.transfer(
        db,
        territory,
        second.id,
        changed_at=changed_at,
        reason="war_victory",
        war_id=None,
    )
    db.commit()

    rows = (
        db.query(TerritoryOwnershipHistory)
        .filter(TerritoryOwnershipHistory.territory_id == territory.id)
        .order_by(TerritoryOwnershipHistory.started_at)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].clan_id == first.id
    assert as_utc(rows[0].ended_at) == changed_at
    assert rows[1].clan_id == second.id
    assert rows[1].ended_at is None
    assert as_utc(territory.owned_since) == changed_at
    assert as_utc(territory.resource_income_ready_at) == changed_at + timedelta(hours=48)
    assert territory.last_resource_payout_at is None
    assert first.territory_points == 100
    assert second.territory_points == 140


def test_resources_start_after_48_hours_then_pay_daily_and_are_idempotent(
    db,
    monkeypatch,
):
    clan = add_clan(db, "Суточная экономика")
    captured_at = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
    territory = add_territory(db, "Суточная земля", resource_output=1)
    TerritoryOwnershipService().transfer(
        db,
        territory,
        clan.id,
        changed_at=captured_at,
        reason="test_capture",
    )
    clan.last_economy_tick = captured_at
    db.commit()

    service = ClanEconomyService()
    monkeypatch.setattr(
        "app.services.clan_economy_service.utc_now",
        lambda: captured_at + timedelta(hours=47, minutes=59),
    )
    service.settle_clan(db, clan)
    db.commit()
    assert clan.mithril == 0
    assert clan.territory_points == 140

    payout_at = captured_at + timedelta(hours=48)
    monkeypatch.setattr(
        "app.services.clan_economy_service.utc_now",
        lambda: payout_at,
    )
    service.settle_clan(db, clan)
    db.commit()

    assert clan.mithril == 1
    assert clan.territory_points == 140
    assert as_utc(territory.last_resource_payout_at) == payout_at
    assert db.query(ResourceLedgerEntry).filter_by(
        action="territory_daily_resource"
    ).count() == 1
    assert db.query(ResourceLedgerEntry).filter_by(
        action="territory_weekly_influence"
    ).count() == 0

    service.settle_clan(db, clan)
    db.commit()
    assert clan.mithril == 1
    assert clan.territory_points == 140
    assert db.query(ResourceLedgerEntry).filter_by(
        action="territory_daily_resource"
    ).count() == 1

    monkeypatch.setattr(
        "app.services.clan_economy_service.utc_now",
        lambda: payout_at + timedelta(hours=24),
    )
    service.settle_clan(db, clan)
    db.commit()
    assert clan.mithril == 2
    assert db.query(ResourceLedgerEntry).filter_by(
        action="territory_daily_resource"
    ).count() == 2


def test_admin_influence_change_recalculates_current_owner(db):
    clan = add_clan(db, "Владелец редактируемой земли")
    territory = add_territory(db, "Редактируемая земля")
    TerritoryOwnershipService().transfer(
        db,
        territory,
        clan.id,
        reason="test_capture",
    )
    db.commit()
    assert clan.territory_points == 140

    TerritoryRepository(db).update(
        territory.id,
        TerritoryUpdate(influence_value=125),
    )

    assert territory.influence_value == 125
    assert clan.territory_points == 225


def test_admin_attack_influence_requirement_is_independent_from_owner_bonus(db):
    clan = add_clan(db, "Владелец земли с отдельным порогом атаки")
    territory = add_territory(
        db,
        "Земля с отдельным порогом атаки",
        required_influence=375,
    )
    TerritoryOwnershipService().transfer(
        db,
        territory,
        clan.id,
        reason="test_capture",
    )
    db.commit()

    TerritoryRepository(db).update(
        territory.id,
        TerritoryUpdate(
            influence_value=90,
            required_influence=800,
        ),
    )

    assert territory.influence_value == 90
    assert territory.required_influence == 800
    assert clan.territory_points == 190
    assert get_attack_influence_cost(territory) == 800


def test_daily_gold_income_uses_capped_population_percentage():
    territory = Territory(
        name="Процентная экономика",
        region="gondor",
        svg_path_data="M 0 0 L 2 0 L 1 1 Z",
        resource_wealth=1,
        population=500,
        strategic_value=10,
        development_level=10,
        fortifications=10,
        stronghold_power=10,
    )

    assert territory.population_income_bonus_percent == 5
    assert territory.population_development_income_bonus_percent == 60
    assert territory.daily_income == 1.65

    territory.population = 5_000
    assert territory.population_income_bonus_percent == 20
    assert territory.daily_income == 1.8

    territory.resource_wealth = 0
    assert territory.daily_income == 0


def test_fractional_daily_gold_income_is_preserved(db, monkeypatch):
    clan = add_clan(db, "Клан малой экономики")
    captured_at = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
    territory = add_territory(
        db,
        "Земля с единичным доходом",
        resource_wealth=1,
        population=0,
    )
    TerritoryOwnershipService().transfer(
        db,
        territory,
        clan.id,
        changed_at=captured_at,
        reason="test_capture",
    )
    clan.last_economy_tick = captured_at
    db.commit()

    service = ClanEconomyService()
    for day in range(1, 8):
        monkeypatch.setattr(
            "app.services.clan_economy_service.utc_now",
            lambda day=day: captured_at + timedelta(days=day),
        )
        service.settle_clan(db, clan)
        db.commit()

    assert clan.gold == 107
    assert clan.gold_income_remainder == 0
    assert db.query(ResourceLedgerEntry).filter_by(
        action="territory_income"
    ).count() == 7


def test_strategic_value_is_average_of_available_upgrade_levels(db):
    ordinary = add_territory(
        db,
        "Обычная развиваемая земля",
        development_level=0,
        fortifications=0,
        offense_level=0,
    )
    assert ordinary.calculate_strategic_value() == 0

    ordinary.development_level = 10
    ordinary.fortifications = 10
    ordinary.offense_level = 10
    assert ordinary.calculate_strategic_value() == 10

    ordinary.development_level = 3
    ordinary.fortifications = 6
    ordinary.offense_level = 9
    assert ordinary.calculate_strategic_value() == 6

    port = add_territory(
        db,
        "Портовая развиваемая земля",
        has_port=True,
        development_level=10,
        fortifications=10,
        offense_level=10,
        port_level=0,
        fleet_level=0,
    )
    assert port.calculate_strategic_value() == 7.5

    port.port_level = 10
    port.fleet_level = 10
    assert port.calculate_strategic_value() == 10
