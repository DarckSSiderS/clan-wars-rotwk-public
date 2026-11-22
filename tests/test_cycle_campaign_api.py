from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.cycle_campaign import router
from app.core.auth import get_current_active_user, get_current_admin_user
from app.database import get_db
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_plan_service import CyclePlanService
from tests.test_cycle_plan_service import setup_world
from tests.test_cycle_battle_service import revealed
from app.services.cycle_battle_service import CycleBattleService


def client_for(db, user, *, admin=False):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: user
    if admin:
        app.dependency_overrides[get_current_admin_user] = lambda: user
    return TestClient(app)


def test_cycle_status_does_not_expose_private_orders_or_snapshot(db):
    users, clan, land, cycle = setup_world(db)
    client = client_for(db, users[3])
    response = client.get(f'/cycles/{cycle.id}')
    assert response.status_code == 200
    assert response.json()['rule_version'] == 2
    assert 'planning_snapshot' not in response.json()
    assert 'orders' not in response.json()
    assert 'dependencies' not in response.json()


def test_next_cycle_start_is_public_only_after_settlement_and_not_after_season_end(db, monkeypatch):
    users, _, _, cycle = setup_world(db)
    deadline = CampaignCycleStore.timeline(cycle).replay_deadline
    now = deadline + timedelta(hours=2)
    monkeypatch.setattr('app.api.v1.cycle_campaign.utc_now', lambda: now)
    client = client_for(db, users[3])
    url = f'/cycles/{cycle.id}'
    assert client.get(url).json()['next_cycle_starts_at'] is None

    cycle.settled_at = now - timedelta(hours=1)
    db.flush()
    status = client.get(url).json()
    assert status['phase'] == 'rest'
    assert datetime.fromisoformat(status['next_cycle_starts_at']) == cycle.settled_at + timedelta(hours=12)

    cycle.season_end_requested = True
    db.flush()
    assert client.get(url).json()['next_cycle_starts_at'] is None


def test_plan_api_denies_foreign_member_and_serializes_own_plan(db, monkeypatch):
    users, clan, land, cycle = setup_world(db)
    now = CampaignCycleStore.timeline(cycle).preparation_at
    monkeypatch.setattr('app.api.v1.cycle_campaign.utc_now', lambda: now)
    CyclePlanService().capture_preparation(db, cycle_id=cycle.id, now=now)
    client = client_for(db, users[0])
    url = f'/cycles/{cycle.id}/clans/{clan.id}/plan'
    response = client.put(url, json={'expected_revision': 0, 'orders': [
        {'user_id': users[2].id, 'kind': 'defend', 'territory_id': land.id}
    ]})
    assert response.status_code == 200
    assert response.json()['revision'] == 1
    assert client.put(url, json={'expected_revision': 0, 'orders': []}).status_code == 409
    foreign = client_for(db, users[3])
    assert foreign.get(url).status_code == 403
    assert foreign.put(url, json={'expected_revision': 1, 'orders': []}).status_code == 403


def test_ordinary_user_cannot_request_season_end(db):
    users, _, _, cycle = setup_world(db)
    response = client_for(db, users[2]).post(f'/cycles/{cycle.id}/request-season-end')
    assert response.status_code in (401, 403)


def test_multiside_battle_api_has_sides_and_admin_only_adjustments(db):
    users, clan, other, _, cycle = revealed(db)
    battle = CycleBattleService().create_from_orders(db, cycle_id=cycle.id)[0]
    client = client_for(db, users[2])
    response = client.get(f'/cycles/{cycle.id}/battles')
    assert response.status_code == 200
    assert len(response.json()['battles'][0]['sides']) == 2
    url = f'/cycles/battles/{battle.id}/adjustments'
    payload = {'clan_id': other.id, 'amount': '10.125', 'command_id': 'test:1', 'reason': 'Correction'}
    assert client.post(url, json=payload).status_code in (401, 403)
    admin = client_for(db, users[0], admin=True)
    assert admin.post(url, json=payload).status_code == 200
    assert admin.post(url, json=payload).status_code == 200
    detail = admin.get(f'/cycles/battles/{battle.id}').json()
    assert next(s for s in detail['sides'] if s['clan_id'] == other.id)['score'] == '10.125000000000'


def test_personal_calculation_metadata_is_visible_in_match_detail(db):
    from tests.test_cycle_match_service import match_world
    from app.services.cycle_match_service import CycleMatchService
    users, _, _, _, battle, facts = match_world(db)
    CycleMatchService().process(db, battle_id=battle.id, replay=facts)
    response = client_for(db, users[2]).get(f'/cycles/battles/{battle.id}')
    assert response.status_code == 200
    rows = response.json()['contributions']
    assert rows[0]['calculation']['historical_elo'] == '1000'
    assert rows[0]['calculation']['direct_multiplier'] == 2
    assert not {'uuid', 'source', 'input_fingerprint', 'structure_fingerprint'}.intersection(rows[0]['calculation'])
    assert '1000' not in str(response.json().get('fallback_elo', ''))
