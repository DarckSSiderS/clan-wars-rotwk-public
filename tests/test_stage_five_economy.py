from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import InsufficientPermissionsException
from app.models.campaign import CampaignRuleSet
from app.models.clan import Clan, ClanMember
from app.models.clan_asset import ClanAsset
from app.models.operation import ResourceLedgerEntry
from app.models.territory import Territory
from app.models.user import User
from app.services.clan_economy_service import ClanEconomyService
from app.services.territory_ownership_service import TerritoryOwnershipService


def test_great_stronghold_gives_two_different_resources(db, monkeypatch):
    clan = Clan(
        name="Хранители великой крепости",
        base_influence=100,
        territory_points=100,
        gold=0,
        resources=0,
        iron=0,
        wood=0,
        food=0,
        mithril=0,
    )
    territory = Territory(
        name="Великая крепость",
        region="gondor",
        svg_path_data="M 0 0 L 2 0 L 1 1 Z",
        resource_type="mithril",
        resource_output=8,
        secondary_resource_type="food",
        stronghold_power=4,
        influence_value=40,
    )
    db.add_all([clan, territory])
    db.commit()

    captured_at = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
    TerritoryOwnershipService().transfer(
        db,
        territory,
        clan.id,
        changed_at=captured_at,
        reason="test_capture",
    )
    clan.last_economy_tick = captured_at
    db.commit()

    monkeypatch.setattr(
        "app.services.clan_economy_service.utc_now",
        lambda: captured_at + timedelta(hours=48),
    )
    ClanEconomyService().settle_clan(db, clan)
    db.commit()

    assert clan.mithril == 1
    assert clan.food == 1
    entries = (
        db.query(ResourceLedgerEntry)
        .filter_by(action="territory_daily_resource")
        .all()
    )
    assert {(entry.resource, entry.amount) for entry in entries} == {
        ("mithril", 1),
        ("food", 1),
    }


def test_relic_requires_influence_but_does_not_spend_it(db):
    leader = User(
        username="relic-leader",
        email="relic-leader@example.com",
        hashed_password="unused",
        is_active=True,
    )
    db.add(leader)
    db.flush()
    clan = Clan(
        name="Искатели реликвий",
        leader_id=leader.id,
        base_influence=249,
        territory_points=249,
        gold=10000,
        resources=10000,
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
    asset = ClanAsset(
        key="test_relic",
        name="Испытательная реликвия",
        bonus_type="attack_power",
        bonus_value=1,
        gold_cost=10,
        required_influence_level_1=250,
        required_influence_level_2=750,
        required_influence_level_3=1500,
    )
    db.add(asset)
    db.commit()

    service = ClanEconomyService()
    with pytest.raises(InsufficientPermissionsException):
        service.purchase_asset(db, clan.id, asset.id, leader)

    clan.base_influence = 250
    clan.territory_points = 250
    db.commit()
    owned = service.purchase_asset(db, clan.id, asset.id, leader)

    assert owned.level == 1
    assert clan.territory_points == 250
    assert clan.base_influence == 250
    assert clan.gold == 9990


def test_relic_catalog_uses_the_same_versioned_price_as_purchase(db):
    leader = User(
        username="versioned-relic-leader",
        email="versioned-relic-leader@example.com",
        hashed_password="unused",
        is_active=True,
    )
    db.add(leader)
    db.flush()
    clan = Clan(
        name="Хранители версий",
        leader_id=leader.id,
        base_influence=2000,
        territory_points=2000,
        gold=1000,
        resources=1000,
        iron=100,
        wood=100,
        food=100,
        mithril=100,
    )
    asset = ClanAsset(
        key="versioned_relic",
        name="Версионная реликвия",
        bonus_type="attack_power",
        bonus_value=1,
        gold_cost=10,
        required_influence_level_1=0,
        required_influence_level_2=0,
        required_influence_level_3=0,
    )
    db.add_all([clan, asset])
    db.flush()
    db.add(ClanMember(clan_id=clan.id, user_id=leader.id, rank="Глава клана"))
    db.commit()

    service = ClanEconomyService()
    first_level = service.purchase_asset(db, clan.id, asset.id, leader)
    assert first_level.level == 1
    assert clan.gold == 990

    active_rules = db.query(CampaignRuleSet).filter_by(is_active=True).one()
    updated_values = dict(active_rules.values)
    updated_values["RELIC_LEVEL_2_COST_MULTIPLIER"] = 7
    active_rules.values = updated_values
    db.commit()

    listed = service.list_assets(db, clan.id)
    assert listed[0]["next_cost_multiplier"] == 7
    assert listed[0]["next_costs"] == {
        "gold": 70,
        "iron": 0,
        "wood": 0,
        "food": 0,
        "mithril": 0,
    }

    second_level = service.purchase_asset(db, clan.id, asset.id, leader)
    assert second_level.level == 2
    assert clan.gold == 920


def test_territory_economy_exposes_periods_for_map_panel(db):
    territory = Territory(
        name="Панельная земля",
        region="gondor",
        svg_path_data="M 0 0 L 3 0 L 1 2 Z",
        resource_wealth=14,
        resource_type="wood",
        resource_output=2,
        influence_value=8,
        population=5000,
    )
    db.add(territory)
    db.commit()

    economy = ClanEconomyService().get_territory_economy(territory, db)

    assert economy["gold_income_period_hours"] == 24
    assert economy["resource_ready_period_hours"] == 48
    assert economy["resource_payout_period_hours"] == 24
    assert economy["daily_income"] == 16.8
    assert economy["daily_resource_rewards"] == [
        {"resource": "wood", "amount": 2},
    ]
