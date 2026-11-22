"""Проверки географии подкреплений на отдельной SQLite без обращения к сети."""
import copy
from datetime import datetime, timedelta

import pytest

from app.models.territory import Territory
from app.services.cycle_reinforcement_store import CycleReinforcementStore
from tests.test_cycle_reinforcement_store import world, initialize, request, send, T
from tests.test_cycle_operations_api import client_for, path, no_network


@pytest.fixture
def geography(db, world):
    _, clans, target, _ = world
    origin = Territory(name='Origin', region='Local', owner_clan_id=clans[0].id,
                       svg_path_data='M0 0h10v10h-10z', is_playable=True)
    middle = Territory(name='Middle', region='Local', svg_path_data='M10 0h10v10h-10z', is_playable=True)
    other = Territory(name='Other origin', region='Local', owner_clan_id=clans[0].id,
                      svg_path_data='M0 10h10v10h-10z', is_playable=True)
    db.add_all([origin, middle, other])
    db.flush()
    origin.adjacent_territory_ids = [middle.id]
    middle.adjacent_territory_ids = [origin.id, target.id, other.id]
    other.adjacent_territory_ids = [middle.id]
    target.adjacent_territory_ids = [middle.id]
    target.svg_path_data = 'M20 0h10v10h-10z'
    db.flush()
    return origin, middle, other


def ready_client(db, world, monkeypatch):
    initialize(db, world)
    request(db, world)
    db.commit()
    client, _ = client_for(db, monkeypatch, world[0][0], T)
    url = path(world[3], world[1][0]) + '/reinforcements'
    body = dict(dispatch_id='geographic', request_id='q', recipient_clan_id=world[1][1].id,
                territory_id=world[2].id, player_user_ids=[world[0][1].id], expected_revision=2)
    return client, url, body


def test_dispatch_freezes_real_graph_route_and_keeps_24h_and_target_interception(db, world, geography, monkeypatch):
    origin, middle, _ = geography
    client, url, body = ready_client(db, world, monkeypatch)
    body['origin_territory_id'] = origin.id
    response = client.post(url + '/dispatches', json=body)
    assert response.status_code == 200, response.text
    dispatch = response.json()['dispatches'][0]
    route = dispatch['route']
    assert route['status'] == 'mapped'
    assert route['territory_ids'] == [origin.id, middle.id, world[2].id]
    assert route['origin_territory_id'] == origin.id
    assert [node['svg_path_data'] for node in route['nodes']] == [origin.svg_path_data, middle.svg_path_data, world[2].svg_path_data]
    assert dispatch['arrives_at'] == (T + timedelta(hours=24)).isoformat()
    # Interception remains tied to the target battle, not traversed lands.
    context = client.get(url + '/context').json()
    assert datetime.fromisoformat(context['state']['dispatches'][0]['interception_at']) == T + timedelta(hours=2)
    frozen = copy.deepcopy(route)
    from app.services.cycle_map_service import CycleMapService
    assert CycleMapService().read(db, cycle_id=world[3].id, actor_user_id=world[0][7].id,
                                  now=T)['dispatches'][0]['route'] == frozen
    origin.owner_clan_id = world[1][2].id
    middle.adjacent_territory_ids = []
    middle.svg_path_data = 'M999 999'
    db.commit()
    retry = client.post(url + '/dispatches', json={**body, 'expected_revision': 1})
    assert retry.status_code == 200
    assert retry.json()['dispatches'][0]['route'] == frozen
    assert client.get(url).json()['dispatches'][0]['route'] == frozen


@pytest.mark.parametrize('origin_kind', ['missing', 'foreign', 'nonplayable', 'invalid_type'])
def test_origin_is_required_only_when_own_playable_lands_exist_and_validated_live(db, world, geography, monkeypatch, origin_kind):
    origin, _, _ = geography
    client, url, body = ready_client(db, world, monkeypatch)
    if origin_kind == 'foreign':
        body['origin_territory_id'] = world[2].id
    elif origin_kind == 'invalid_type':
        body['origin_territory_id'] = True
    elif origin_kind == 'nonplayable':
        origin.is_playable = False
        db.commit()
        body['origin_territory_id'] = origin.id
    response = client.post(url + '/dispatches', json=body)
    assert response.status_code == 409
    assert client.get(url).json()['dispatches'] == []


def test_retry_payload_includes_origin_even_if_route_is_now_unreachable(db, world, geography, monkeypatch):
    origin, _, other = geography
    client, url, body = ready_client(db, world, monkeypatch)
    body['origin_territory_id'] = origin.id
    assert client.post(url + '/dispatches', json=body).status_code == 200
    for changed in [other.id, None]:
        assert client.post(url + '/dispatches', json={**body, 'origin_territory_id': changed}).status_code == 409
    assert len(client.get(url).json()['dispatches']) == 1


def test_context_lists_live_origins_and_real_previews_without_writing(db, world, geography, monkeypatch):
    origin, middle, other = geography
    client, url, _ = ready_client(db, world, monkeypatch)
    data = client.get(url + '/context').json()
    assert {item['territory_id'] for item in data['origins']} == {origin.id, other.id}
    route = next(r for r in data['route_previews'] if r['origin_territory_id'] == origin.id and r['target_territory_id'] == world[2].id)
    assert route['territory_ids'] == [origin.id, middle.id, world[2].id]
    assert data['state']['revision'] == 2
    origin.owner_clan_id = world[1][1].id
    db.commit()
    assert origin.id not in {item['territory_id'] for item in client.get(url + '/context').json()['origins']}


def test_disconnected_map_does_not_invent_a_line_or_reject_dispatch(db, world, geography, monkeypatch):
    origin, middle, _ = geography
    middle.adjacent_territory_ids = [origin.id]
    world[2].adjacent_territory_ids = []
    client, url, body = ready_client(db, world, monkeypatch)
    response = client.post(url + '/dispatches', json={**body, 'origin_territory_id': origin.id})
    assert response.status_code == 200, response.text
    route = response.json()['dispatches'][0]['route']
    assert route['status'] == 'unreachable' and route['territory_ids'] == []
    assert [node['territory_id'] for node in route['nodes']] == [world[2].id]


def test_landless_dispatch_has_only_target_and_timer_and_rejects_fabricated_origin(db, world, monkeypatch):
    client, url, body = ready_client(db, world, monkeypatch)
    data = client.get(url + '/context').json()
    assert data['origins'] == []
    assert client.post(url + '/dispatches', json={**body, 'origin_territory_id': world[2].id}).status_code == 409
    response = client.post(url + '/dispatches', json=body)
    assert response.status_code == 200
    route = response.json()['dispatches'][0]['route']
    assert route['status'] == 'no_origin' and route['origin_territory_id'] is None
    assert route['territory_ids'] == []
    assert [node['territory_id'] for node in route['nodes']] == [world[2].id]


def test_legacy_dispatch_without_route_remains_readable_and_retryable(db, world, monkeypatch):
    client, url, body = ready_client(db, world, monkeypatch)
    send(db, world, command='legacy')
    db.commit()
    # Имитируем прежнюю отправку без отдельной записи маршрута.
    from app.models.cycle_dispatch_route import CycleDispatchRoute
    db.query(CycleDispatchRoute).delete()
    db.commit()
    data = client.get(url).json()
    assert data['dispatches'][0]['route'] is None
    db.add(Territory(name='Newly acquired', region='Local', svg_path_data='M0 0h10v10h-10z',
                     owner_clan_id=world[1][0].id, is_playable=True))
    db.commit()
    retry = client.post(url + '/dispatches', json={**body, 'dispatch_id': 'legacy'})
    assert retry.status_code == 200
    assert retry.json()['dispatches'][0]['route'] is None
    assert db.query(CycleDispatchRoute).count() == 0


def test_route_and_aggregate_share_transaction_and_stale_revision_writes_neither(db, world, geography, monkeypatch):
    from app.models.cycle_dispatch_route import CycleDispatchRoute
    origin, _, _ = geography
    client, url, body = ready_client(db, world, monkeypatch)
    response = client.post(url + '/dispatches', json={**body, 'origin_territory_id': origin.id, 'expected_revision': 1})
    assert response.status_code == 409
    assert db.query(CycleDispatchRoute).count() == 0
    assert client.get(url).json()['dispatches'] == []
    store = CycleReinforcementStore()
    store.dispatch(db, cycle_id=world[3].id, dispatch_id='rolled-back', sender_clan_id=world[1][0].id,
        recipient_clan_id=world[1][1].id, territory_id=world[2].id, player_user_ids=[world[0][1].id],
        actor_user_id=world[0][0].id, now=T, request_id='q', origin_territory_id=origin.id, expected_revision=2)
    assert db.query(CycleDispatchRoute).count() == 1
    db.rollback()
    assert db.query(CycleDispatchRoute).count() == 0
    assert client.get(url).json()['dispatches'] == []


def test_graph_excludes_nonplayable_shortcuts_and_has_deterministic_ties(db, world, geography, monkeypatch):
    origin, middle, other = geography
    shortcut = Territory(name='Water', region='Local', svg_path_data='M0 0', is_playable=False,
                         adjacent_territory_ids=[world[2].id])
    db.add(shortcut)
    db.flush()
    origin.adjacent_territory_ids = [shortcut.id, other.id, middle.id]
    other.adjacent_territory_ids = [world[2].id]
    client, url, body = ready_client(db, world, monkeypatch)
    response = client.post(url + '/dispatches', json={**body, 'origin_territory_id': origin.id})
    assert response.status_code == 200
    assert response.json()['dispatches'][0]['route']['territory_ids'] == [origin.id, middle.id, world[2].id]


def test_choosing_target_as_own_origin_is_valid_without_inventing_a_loop(db, world, geography, monkeypatch):
    _, _, other = geography
    other.owner_clan_id = None
    geography[0].owner_clan_id = None
    world[2].owner_clan_id = world[1][0].id
    client, url, body = ready_client(db, world, monkeypatch)
    response = client.post(url + '/dispatches', json={**body, 'origin_territory_id': world[2].id})
    assert response.status_code == 200
    assert response.json()['dispatches'][0]['route']['territory_ids'] == [world[2].id]
