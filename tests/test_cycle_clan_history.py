from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.database import get_db
from app.models.campaign import CampaignSeason
from app.models.cycle_battle import CycleTerritoryBattle
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_battle_service import CycleBattleService
from tests.test_cycle_battle_service import revealed


def client_for(db, user=None):
    from app.api.v1.cycle_clan_history import router
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.dependency_overrides[get_db] = lambda: db
    if user:
        app.dependency_overrides[get_current_active_user] = lambda: user
    return TestClient(app)


def test_history_uses_revealed_clan_ids_not_names_and_has_public_scores(db):
    users, clan, other, land, cycle = revealed(db)
    service = CycleBattleService()
    battle = service.create_from_orders(db, cycle_id=cycle.id)[0]
    service.record_contribution(db, battle_id=battle.id, replay_id='one', user_id=users[2].id,
                                clan_id=clan.id, points=25, reason='counted')
    clan.name = 'Renamed clan'
    users[2].username = 'Renamed player'
    response = client_for(db, users[3]).get(f'/api/v1/campaign/cycles/clans/{clan.id}/history')
    assert response.status_code == 200
    data = response.json()
    assert data['season_id'] == cycle.season_id
    assert len(data['battles']) == 1
    row = data['battles'][0]
    assert (row['id'], row['cycle_id'], row['territory_id']) == (battle.id, cycle.id, land.id)
    assert row['season_id'] == cycle.season_id
    own = next(side for side in row['sides'] if side['clan_id'] == clan.id)
    assert own['clan_name'] == 'Renamed clan'
    assert float(own['score']) == 25
    assert not {'orders', 'user_ids', 'uuid', 'members', 'planning_snapshot'} & set(own)
    assert 'contributions' not in row


def test_history_hides_unregistered_and_unfrozen_battles_and_other_clans(db):
    users, clan, other, _, cycle = revealed(db)
    CycleBattleService().create_from_orders(db, cycle_id=cycle.id)
    client = client_for(db, users[0])
    assert client.get(f'/api/v1/campaign/cycles/clans/{clan.id}/history').json()['battles']
    cycle.battles_registered = False
    db.flush()
    assert client.get(f'/api/v1/campaign/cycles/clans/{clan.id}/history').json()['battles'] == []
    cycle.battles_registered = True
    cycle.orders_frozen_at = None
    db.flush()
    assert client.get(f'/api/v1/campaign/cycles/clans/{clan.id}/history').json()['battles'] == []
    cycle.orders_frozen_at = CampaignCycleStore.timeline(cycle).battle_at
    row = db.query(CycleTerritoryBattle).one()
    row.sides = [side for side in row.sides if side['clan_id'] == other.id]
    db.flush()
    assert client.get(f'/api/v1/campaign/cycles/clans/{clan.id}/history').json()['battles'] == []


def test_archived_cycles_remain_visible_without_initializing_or_changing_anything(db):
    users, clan, _, _, cycle = revealed(db)
    battle = CycleBattleService().create_from_orders(db, cycle_id=cycle.id)[0]
    battle.completed_at = CampaignCycleStore.timeline(cycle).replay_deadline
    battle.winner_clan_id = clan.id
    season = db.get(CampaignSeason, cycle.season_id)
    season.status = 'completed'
    db.flush()
    data = client_for(db, users[0]).get(f'/api/v1/campaign/cycles/clans/{clan.id}/history').json()
    assert data['battles'][0]['winner_clan_id'] == clan.id
    assert data['battles'][0]['completed_at'] is not None
    assert db.query(CycleTerritoryBattle).count() == 1
    season.rules_snapshot = {'mechanics_version': 'legacy'}
    db.flush()
    assert client_for(db, users[0]).get(f'/api/v1/campaign/cycles/clans/{clan.id}/history').json()['battles'] == []


def test_history_requires_auth_and_unknown_clan_is_404(db):
    users, _, _, _, _ = revealed(db)
    assert client_for(db).get('/api/v1/campaign/cycles/clans/1/history').status_code == 401
    assert client_for(db, users[0]).get('/api/v1/campaign/cycles/clans/999999/history').status_code == 404
