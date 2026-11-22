"""Local-only HTTP contract tests using real services and disposable SQLite."""
import socket
import inspect
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.database import get_db
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_economy_store import CycleEconomyStore
from tests.test_cycle_plan_service import setup_world
from tests.test_cycle_reinforcement_store import world, initialize, T
from tests.test_cycle_startup_service import startup, initialize as initialize_startup, NOW


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    original = socket.socket.connect

    def denied(sock, address):
        # Windows asyncio constructs its local wakeup pipe via socketpair().
        if any(frame.function in ('socketpair', '_fallback_socketpair') and frame.filename == socket.__file__
               for frame in inspect.stack()):
            return original(sock, address)
        raise AssertionError('Network forbidden in operations API tests')
    monkeypatch.setattr(socket.socket, 'connect', denied)


def client_for(db, monkeypatch, user, now):
    from app.api.v1 import cycle_operations as api
    monkeypatch.setattr(api, 'utc_now', lambda: now)
    user.onboarding_completed_at = now
    app = FastAPI()
    app.include_router(api.router, prefix='/api/v1/campaign/cycles')
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: user
    return TestClient(app), app


def path(cycle, clan):
    return f'/api/v1/campaign/cycles/{cycle.id}/clans/{clan.id}'


def test_scout_retry_private_report_and_server_clock(db, monkeypatch):
    users, clan, land, cycle = setup_world(db)
    state = CycleEconomyStore().ensure_state(db, season_id=cycle.season_id, clan_id=clan.id)
    now = CampaignCycleStore.timeline(cycle).preparation_at
    db.commit()
    client, app = client_for(db, monkeypatch, users[1], now)
    url = path(cycle, clan) + '/scout'
    body = {'territory_id': land.id, 'scout_user_id': users[2].id, 'expected_revision': state.revision}
    first = client.post(url, json=body)
    assert first.status_code == 200
    assert set(first.json()) == {'id', 'cycle_id', 'clan_id', 'territory_id', 'requested_at', 'scout_user_id', 'scout_uuid'}
    assert client.post(url, json=body).json() == first.json()
    app.dependency_overrides[get_current_active_user] = lambda: users[2]
    assert client.post(url, json=body).status_code == 403
    report = url + f'/{first.json()["id"]}/report'
    assert client.get(report).json() == {'report': None}
    from app.api.v1 import cycle_operations as api
    monkeypatch.setattr(api, 'utc_now', lambda: now + timedelta(days=2))
    assert client.get(report).json() == {'report': {'enemy_squads': []}}
    assert client.get(report.replace(f'/{cycle.id}/clans', '/999/clans')).status_code == 409
    app.dependency_overrides[get_current_active_user] = lambda: users[3]
    assert client.get(report).status_code == 403


def test_reinforcement_permissions_retries_projection_and_conflicts(db, world, monkeypatch):
    users, clans, land, cycle = world
    initialize(db, world)
    db.commit()
    client, app = client_for(db, monkeypatch, users[3], T)
    recipient = path(cycle, clans[1]) + '/reinforcements'
    body = {'request_id': 'help-1', 'territory_id': land.id, 'expected_revision': 1}
    assert client.post(recipient + '/requests', json=body).status_code == 200
    assert client.post(recipient + '/requests', json=body).json()['revision'] == 2
    app.dependency_overrides[get_current_active_user] = lambda: users[0]
    sender = path(cycle, clans[0]) + '/reinforcements'
    assert client.get(sender).json()['ambushes'] == []
    dispatch = dict(dispatch_id='send-1', request_id='help-1', recipient_clan_id=clans[1].id,
                    territory_id=land.id, player_user_ids=[users[1].id], expected_revision=1)
    assert client.post(sender + '/dispatches', json=dispatch).status_code == 409
    dispatch['expected_revision'] = 2
    response = client.post(sender + '/dispatches', json=dispatch)
    assert response.status_code == 200
    assert client.post(sender + '/dispatches', json=dispatch).json() == response.json()
    data = response.json()
    assert set(data) == {'revision', 'reserves', 'ambushes', 'dispatches', 'requests'}
    assert all(r['clan_id'] == clans[0].id for r in data['reserves'])
    assert data['ambushes'][0]['dispatch_id'] == 'send-1'
    app.dependency_overrides[get_current_active_user] = lambda: users[1]
    assert client.get(sender).status_code == 200
    assert client.post(sender + '/dispatches', json=dispatch).status_code == 403
    assert client.get(recipient).status_code == 403


def test_startup_head_only_preview_claim_retry_and_no_initializer(db, startup, monkeypatch):
    from types import SimpleNamespace
    service, cycle, _, clans, lands = startup
    lands[0].owner_clan_id = clans[0].id
    db.flush()
    initialize_startup(db, startup)
    db.commit()
    client, app = client_for(db, monkeypatch, SimpleNamespace(id=100), NOW + timedelta(hours=1))
    url = path(cycle, clans[0]) + '/startup'
    body = {'selected': [t.id for t in lands[:3]]}
    assert client.post(url + '/preview', json=body).status_code == 200
    assert client.post(url + '/claim', json={**body, 'expected_revision': 99}).status_code == 409
    body['expected_revision'] = 1
    response = client.post(url + '/claim', json=body)
    assert response.status_code == 200
    assert set(response.json()) == {'clan_id', 'revision', 'status', 'selected_lands', 'claimed_at'}
    assert client.post(url + '/claim', json=body).json() == response.json()
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id=101, onboarding_completed_at=NOW)
    assert client.post(url + '/claim', json=body).status_code == 403
    assert client.post(url + '/preview', json={'selected': body['selected']}).status_code == 403
    assert client.post(url + '/initialize').status_code == 404


def test_voivode_help_and_dispatch_use_database_rights(db, world, monkeypatch):
    users, clans, land, cycle = world
    initialize(db, world)
    db.commit()
    client, app = client_for(db, monkeypatch, users[3], T)
    recipient = path(cycle, clans[1]) + '/reinforcements/requests'
    body = {'request_id': 'voivode-help', 'territory_id': land.id, 'expected_revision': 1}
    app.dependency_overrides[get_current_active_user] = lambda: users[4]
    assert client.post(recipient, json=body).status_code == 403
    app.dependency_overrides[get_current_active_user] = lambda: users[3]
    assert client.post(recipient, json=body).status_code == 200
    app.dependency_overrides[get_current_active_user] = lambda: users[2]
    sender = path(cycle, clans[0]) + '/reinforcements/dispatches'
    command = dict(dispatch_id='voivode-send', request_id='voivode-help',
                   recipient_clan_id=clans[1].id, territory_id=land.id,
                   player_user_ids=[users[1].id], expected_revision=2)
    assert client.post(sender, json=command).status_code == 200
    from app.models.clan import ClanMember
    db.query(ClanMember).filter_by(user_id=users[2].id).update({'is_warlord': False})
    db.commit()
    assert client.post(sender, json=command).status_code == 403


@pytest.mark.parametrize('suffix,body', [
    ('reinforcements/requests', {'request_id': 'q', 'territory_id': 1}),
    ('reinforcements/dispatches', {'dispatch_id': 'd', 'recipient_clan_id': 1,
                                  'territory_id': 1, 'player_user_ids': [1]}),
    ('startup/claim', {'selected': [1, 2, 3]}),
    ('startup/preview', {'selected': [1, 2]}),
])
def test_required_revisions_and_typed_selection(db, monkeypatch, suffix, body):
    from types import SimpleNamespace
    client, _ = client_for(db, monkeypatch, SimpleNamespace(id=1), T)
    assert client.post('/api/v1/campaign/cycles/1/clans/1/' + suffix,
                       json=body).status_code == 409


@pytest.mark.parametrize('body', [{}, {'territory_id': True, 'expected_revision': 1},
    {'territory_id': 1, 'expected_revision': 1, 'now': '2099-01-01'},
    {'territory_id': 1, 'expected_revision': 1, 'is_admin': True}])
def test_closed_typed_commands_reject_client_authority(db, monkeypatch, body):
    from types import SimpleNamespace
    client, _ = client_for(db, monkeypatch, SimpleNamespace(id=1), T)
    assert client.post('/api/v1/campaign/cycles/1/clans/1/scout', json=body).status_code == 409


def test_authentication_and_route_surface(db):
    from app.api.v1.cycle_operations import router
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get('/1/clans/1/reinforcements')
    assert response.status_code in (401, 403)
    assert len(router.routes) == 12
    assert {method for route in router.routes
            if route.path == '/{cycle_id}/clans/{clan_id}/defence-template'
            for method in route.methods} == {'GET', 'PUT'}
    assert all(route.path.count('{cycle_id}') == 1 for route in router.routes)
    assert not any(word in route.path for route in router.routes
                   for word in ('initialize', 'resolve', 'expire', 'qualify'))
