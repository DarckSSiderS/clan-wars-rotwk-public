from datetime import datetime, timedelta, timezone

from app.models.clan import Clan, ClanMember
from app.models.operation import ResourceLedgerEntry
from app.models.territory import Territory
from app.models.user import User
from app.schemas.clan import ClanCreate
from app.services.campaign_rule_service import CampaignRuleService
from app.services.clan_attack_service import (
    get_clan_attack_status,
    get_next_attack_at,
)
from app.services.clan_economy_service import ClanEconomyService
from app.services.clan_service import ClanService
from app.services.territory_ownership_service import TerritoryOwnershipService


def _leader_with_clan(db, suffix: str = "rules"):
    leader = User(
        username=f"leader-{suffix}",
        email=f"leader-{suffix}@example.com",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
    )
    db.add(leader)
    db.flush()
    clan = Clan(
        name=f"Клан {suffix}",
        leader_id=leader.id,
        base_influence=100,
        territory_points=100,
        gold=10_000,
        resources=10_000,
        iron=100,
        wood=100,
        food=100,
        mithril=100,
    )
    db.add(clan)
    db.flush()
    db.add(
        ClanMember(
            clan_id=clan.id,
            user_id=leader.id,
            rank="Глава клана",
        )
    )
    db.commit()
    return leader, clan


def _activate_rules(db, actor, **changes):
    service = CampaignRuleService()
    active = service.get_active(db)
    return service.create_version(
        db,
        expected_version=active.version,
        changes=changes,
        actor_user_id=actor.id,
        reason="Проверка будущих экономических операций",
        commit=True,
    )


def test_attack_cooldown_helpers_use_the_supplied_duration():
    now = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    next_attack_at = get_next_attack_at(cooldown_hours=12, now=now)

    assert next_attack_at == now + timedelta(hours=12)
    status = get_clan_attack_status(
        next_attack_at,
        cooldown_hours=12,
        now=now,
    )
    assert status["attack_cooldown_seconds"] == 12 * 60 * 60
    assert status["attack_cooldown_duration_seconds"] == 12 * 60 * 60


def test_new_clan_uses_current_starting_influence_without_repricing_existing_clans(db):
    existing_leader, existing_clan = _leader_with_clan(db, "existing")
    new_leader = User(
        username="leader-new-rules",
        email="leader-new-rules@example.com",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
    )
    db.add(new_leader)
    db.commit()
    _activate_rules(
        db,
        existing_leader,
        CAMPAIGN_STARTING_INFLUENCE=275,
        CAMPAIGN_STARTING_GOLD=125,
        CAMPAIGN_STARTING_IRON=7,
        CAMPAIGN_STARTING_WOOD=8,
        CAMPAIGN_STARTING_FOOD=4,
        CAMPAIGN_STARTING_MITHRIL=1,
    )

    created = ClanService().create_clan(
        db,
        ClanCreate(name="Новый клан правил"),
        new_leader.id,
    )

    assert created.base_influence == 275
    assert created.territory_points == 275
    assert (created.gold, created.iron, created.wood, created.food, created.mithril) == (
        125,
        7,
        8,
        4,
        1,
    )
    db.refresh(existing_clan)
    assert existing_clan.base_influence == 100
    assert existing_clan.territory_points == 100


def test_upgrade_uses_one_current_rule_version_and_keeps_old_ledger_amount(db):
    leader, clan = _leader_with_clan(db, "upgrade")
    territory = Territory(
        name="Земля меняющейся цены",
        region="gondor",
        svg_path_data="M 0 0 L 2 0 L 1 1 Z",
        owner_clan_id=clan.id,
        development_level=0,
        population=1_000,
        resource_type="iron",
        resource_output=1,
    )
    db.add(territory)
    db.commit()
    economy = ClanEconomyService()

    first = economy.upgrade_territory(db, territory.id, "population", 1, leader)
    assert first["cost"]["gold"] == 100
    assert territory.population == 1_060
    first_gold_entry = (
        db.query(ResourceLedgerEntry)
        .filter_by(action="territory_upgrade", resource="gold")
        .one()
    )
    assert first_gold_entry.amount == -100

    _activate_rules(db, leader, POPULATION_BASE_GOLD_COST=500)
    second = economy.upgrade_territory(db, territory.id, "population", 1, leader)

    assert second["cost"]["gold"] == 525
    gold_entries = (
        db.query(ResourceLedgerEntry)
        .filter_by(action="territory_upgrade", resource="gold")
        .order_by(ResourceLedgerEntry.id)
        .all()
    )
    assert [entry.amount for entry in gold_entries] == [-100, -525]
    assert first_gold_entry.amount == -100


def test_population_development_adds_diminishing_income_bonus(db):
    territory = Territory(
        name="Земля дохода населения",
        region="gondor",
        svg_path_data="M 0 0 L 2 0 L 1 1 Z",
        resource_wealth=40,
        population=500,
        development_level=1,
    )
    db.add(territory)
    db.commit()
    economy = ClanEconomyService()

    level_one = economy.get_territory_economy(territory, db)
    territory.development_level = 6
    level_six = economy.get_territory_economy(territory, db)
    territory.development_level = 10
    level_ten = economy.get_territory_economy(territory, db)

    assert level_one["population_development_income_bonus_percent"] == 8
    assert level_one["daily_income"] == 45.2
    assert level_six["population_development_income_bonus_percent"] == 44
    assert level_six["daily_income"] == 59.6
    assert level_ten["population_development_income_bonus_percent"] == 60
    assert level_ten["daily_income"] == 66.0


def test_population_upgrade_price_depends_on_territory_wealth_and_level(db):
    economy = ClanEconomyService()
    ordinary = Territory(
        name="Обычная земля населения",
        region="gondor",
        svg_path_data="M 0 0 L 2 0 L 1 1 Z",
        resource_wealth=40,
        development_level=0,
    )
    rich = Territory(
        name="Богатая земля населения",
        region="gondor",
        svg_path_data="M 2 0 L 4 0 L 3 1 Z",
        resource_wealth=220,
        development_level=5,
    )
    db.add_all([ordinary, rich])
    db.commit()

    assert economy.get_upgrade_costs(db, ordinary, "population") == {
        "gold": 140,
        "wood": 1,
    }
    assert economy.get_upgrade_costs(db, rich, "population") == {
        "gold": 445,
        "wood": 1,
    }


def test_port_and_fleet_full_upgrade_match_balanced_budget(db):
    economy = ClanEconomyService()
    territory = Territory(
        name="Портовая земля баланса",
        region="gondor",
        svg_path_data="M 0 0 L 2 0 L 1 1 Z",
        has_port=True,
        port_level=0,
        fleet_level=0,
    )
    db.add(territory)
    db.commit()

    assert economy.get_upgrade_costs(db, territory, "port", 10) == {
        "gold": 1175,
        "iron": 5,
        "wood": 5,
    }
    territory.port_level = 10
    assert economy.get_upgrade_costs(db, territory, "fleet", 10) == {
        "gold": 1175,
        "iron": 5,
        "wood": 5,
        "food": 5,
    }


def test_future_settlement_uses_new_tick_and_payout_intervals(db, monkeypatch):
    leader, clan = _leader_with_clan(db, "settlement")
    captured_at = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
    territory = Territory(
        name="Земля ускоренного тика",
        region="gondor",
        svg_path_data="M 0 0 L 2 0 L 1 1 Z",
        resource_type="mithril",
        resource_output=2,
        resource_wealth=14,
        population=0,
    )
    db.add(territory)
    db.flush()
    TerritoryOwnershipService().transfer(
        db,
        territory,
        clan.id,
        changed_at=captured_at,
        reason="test_capture",
    )
    clan.last_economy_tick = captured_at
    db.commit()
    now = captured_at + timedelta(hours=12)
    monkeypatch.setattr("app.services.clan_economy_service.utc_now", lambda: now)
    economy = ClanEconomyService()

    economy.settle_clan(db, clan)
    assert clan.gold == 10_000
    assert clan.mithril == 100

    _activate_rules(
        db,
        leader,
        ECONOMY_TICK_HOURS=12,
        TERRITORY_RESOURCE_READY_HOURS=12,
        TERRITORY_RESOURCE_PAYOUT_HOURS=12,
    )
    economy.settle_clan(db, clan)
    db.commit()

    assert clan.gold == 10_007
    # Изменение правил не пересчитывает уже зафиксированный срок первой добычи.
    assert clan.mithril == 100
    assert clan.last_economy_tick.replace(tzinfo=timezone.utc) == now
    assert db.query(ResourceLedgerEntry).filter_by(
        action="territory_daily_resource"
    ).count() == 0
