from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.cycle_campaign import router
from app.database import get_db
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_battle_service import CycleBattleService
from tests.test_cycle_battle_service import revealed
from tests.test_cycle_campaign_api import client_for
from tests.test_cycle_plan_service import setup_world
from app.services.war_service import ClanWarService
from app.core.exceptions import WarCreationException
from app.models.war import ClanWar
from app.models.campaign import CampaignRuleSet
from app.schemas.war import ClanWarCreate
import pytest


def test_current_cycle_before_reveal_keeps_hidden_orders_and_map_targets_private(db, monkeypatch):
    users, _, _, cycle = setup_world(db)
    monkeypatch.setattr('app.api.v1.cycle_campaign.utc_now', lambda: CampaignCycleStore.timeline(cycle).preparation_at)
    response = client_for(db, users[0]).get('/cycles/current')
    assert response.status_code == 200
    data = response.json()
    assert data['mechanics_version'] == 'cycle_v1'
    assert data['cycle']['id'] == cycle.id
    assert data['territory_battles'] == []
    assert not {'orders', 'planning_snapshot', 'dependencies', 'source_uuid'} & set(data['cycle'])


def test_current_cycle_exposes_only_revealed_current_territory_links(db, monkeypatch):
    users, clan, other, land, cycle = revealed(db)
    battle = CycleBattleService().create_from_orders(db, cycle_id=cycle.id)[0]
    monkeypatch.setattr('app.api.v1.cycle_campaign.utc_now', lambda: CampaignCycleStore.timeline(cycle).battle_at)
    response = client_for(db, users[2]).get('/cycles/current')
    assert response.status_code == 200
    data = response.json()
    assert data['territory_battles'] == [{'battle_id': battle.id, 'territory_id': land.id}]
    assert data['season_status'] == 'active'
    assert data['cycle']['phase'] == 'battle'
    assert 'member_ids' not in str(data)
    assert 'allied_clan_ids' not in str(data)


def test_next_cycle_does_not_link_to_previous_cycle_battles(db, monkeypatch):
    users, _, _, _, cycle = revealed(db)
    CycleBattleService().create_from_orders(db, cycle_id=cycle.id)
    now = CampaignCycleStore.timeline(cycle).replay_deadline
    following = CampaignCycleRecord(season_id=cycle.season_id, number=2, rule_version=2,
        starts_at=now, preparation_at=now)
    db.add(following)
    db.flush()
    monkeypatch.setattr('app.api.v1.cycle_campaign.utc_now', lambda: now)
    data = client_for(db, users[0]).get('/cycles/current').json()
    assert data['cycle']['id'] == following.id
    assert data['territory_battles'] == []


def test_archived_cycle_is_readable_but_has_no_active_map_links(db, monkeypatch):
    users, _, _, _, cycle = revealed(db)
    CycleBattleService().create_from_orders(db, cycle_id=cycle.id)
    db.get(CampaignSeason, cycle.season_id).status = 'completed'
    db.flush()
    monkeypatch.setattr('app.api.v1.cycle_campaign.utc_now', lambda: CampaignCycleStore.timeline(cycle).battle_at)
    data = client_for(db, users[0]).get('/cycles/current').json()
    assert data['mechanics_version'] == 'cycle_v1'
    assert data['cycle']['id'] == cycle.id
    assert data['territory_battles'] == []


def test_legacy_active_season_wins_over_older_cycle_records(db):
    users, _, _, cycle = setup_world(db)
    older = db.get(CampaignSeason, cycle.season_id)
    older.status = 'completed'
    newer = CampaignSeason(number=2, name='Legacy', status='active', starts_at=older.starts_at,
        rules_snapshot={'version': 2})
    db.add(newer)
    db.flush()
    data = client_for(db, users[0]).get('/cycles/current').json()
    assert data['mechanics_version'] == 'legacy'
    assert data['season_id'] == newer.id
    assert data['cycle'] is None
    assert data['territory_battles'] == []


def test_current_lookup_does_not_initialize_missing_cycle_or_require_a_clan(db):
    users, _, _, cycle = setup_world(db)
    db.delete(cycle)
    db.flush()
    data = client_for(db, users[3]).get('/cycles/current').json()
    assert data['mechanics_version'] == 'cycle_v1'
    assert data['cycle'] is None
    assert db.query(CampaignCycleRecord).count() == 0


def test_current_cycle_requires_authentication(db):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    assert TestClient(app).get('/cycles/current').status_code == 401


def test_cycle_season_cannot_spend_resources_through_legacy_war_creation(db):
    users, clan, land, _ = setup_world(db)
    db.commit()
    before = (clan.gold, clan.territory_points, clan.next_attack_at)
    with pytest.raises(WarCreationException) as error:
        ClanWarService().create_war(db, ClanWarCreate(territory_id=land.id,
            expected_rule_version=99, squad_member_ids=[users[0].id], warlord_user_id=users[0].id), users[0])
    assert error.value.detail['code'] == 'cycle_orders_required'
    assert (clan.gold, clan.territory_points, clan.next_attack_at) == before
    assert db.query(ClanWar).count() == 0
    assert db.query(CampaignRuleSet).count() == 0
