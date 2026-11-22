import pytest

from app.models.campaign import CampaignSeason
from app.models.territory import Territory
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_orders import Order
from app.services.cycle_plan_service import CyclePlanService
from tests.test_cycle_plan_service import setup_world
from tests.test_cycle_campaign_api import client_for


def prepared(db):
    users, clan, land, cycle = setup_world(db)
    target = Territory(name='Neighbour', region='Test', svg_path_data='M0 0', is_playable=True)
    remote = Territory(name='Remote', region='Test', svg_path_data='M0 0', is_playable=True)
    db.add_all([target, remote])
    db.flush()
    land.adjacent_territory_ids = [target.id]
    now = CampaignCycleStore.timeline(cycle).preparation_at
    service = CyclePlanService()
    service.capture_preparation(db, cycle_id=cycle.id, now=now)
    return users, clan, land, target, remote, cycle, service, now


def test_planning_context_is_private_and_routes_use_preparation_snapshot(db):
    users, clan, land, target, remote, cycle, service, now = prepared(db)
    land.adjacent_territory_ids = [remote.id]
    db.flush()
    data = service.planning(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id, now=now)
    assert data['editable'] is True
    assert data['limits'] == {'attacks': 2, 'reserves': 2, 'ambush_players': 2}
    assert data['attack_routes'] == [{'territory_id': target.id, 'source_id': land.id, 'route': 'land'}]
    assert data['defence_targets'] == [land.id]
    assert [m['user_id'] for m in data['members']] == [u.id for u in users[:3]]
    assert 'uuid' not in str(data)
    with pytest.raises(PermissionError):
        service.planning(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[3].id, now=now)


def test_planning_roles_freeze_and_stable_player_ids(db):
    users, clan, land, _, _, cycle, service, now = prepared(db)
    users[2].username = 'Renamed'
    for actor, editable in [(users[0], True), (users[1], True), (users[2], False)]:
        data = service.planning(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=actor.id, now=now)
        assert data['editable'] is editable
        assert next(m for m in data['members'] if m['user_id'] == users[2].id)['name'] == 'Renamed'
    service.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
                 expected_revision=0, orders=[Order(users[2].id, 'defend', land.id)], now=now)
    end = CampaignCycleStore.timeline(cycle).battle_at
    service.freeze(db, cycle_id=cycle.id, now=end)
    data = service.planning(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id, now=end)
    assert not data['editable']
    assert data['plan']['orders'][0]['user_id'] == users[2].id


def test_registration_context_has_no_invented_routes(db):
    users, clan, _, cycle = setup_world(db)
    data = CyclePlanService().planning(db, cycle_id=cycle.id, clan_id=clan.id,
                                      actor_user_id=users[0].id, now=CampaignCycleStore.timeline(cycle).starts_at)
    assert not data['snapshot_ready']
    assert not data['editable']
    assert data['attack_routes'] == []


def test_archived_season_plan_cannot_be_saved(db):
    users, clan, _, _, _, cycle, service, now = prepared(db)
    db.get(CampaignSeason, cycle.season_id).status = 'completed'
    db.flush()
    assert not service.planning(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id, now=now)['editable']
    with pytest.raises(ValueError, match='active'):
        service.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
                     expected_revision=0, orders=[], now=now)


def test_planning_api_and_missing_cycle(db, monkeypatch):
    users, clan, _, _, _, cycle, _, now = prepared(db)
    monkeypatch.setattr('app.api.v1.cycle_campaign.utc_now', lambda: now)
    db.commit()
    path = f'/cycles/{cycle.id}/clans/{clan.id}/planning'
    assert client_for(db, users[0]).get(path).json()['editable'] is True
    assert client_for(db, users[3]).get(path).status_code == 403
    assert client_for(db, users[0]).get(f'/cycles/99999/clans/{clan.id}/planning').status_code == 409


def test_landless_routes_exclude_ports_fortresses_and_allies(db):
    from app.models.clan import Clan
    from app.models.cycle_diplomacy import CycleDiplomacyPair
    users, clan, land, target, remote, cycle, service, now = prepared(db)
    ally = Clan(name='Ally', leader_id=users[3].id, level=1)
    db.add(ally)
    db.flush()
    db.add(CycleDiplomacyPair(season_id=cycle.season_id, clan_low_id=clan.id, clan_high_id=ally.id, allied_at=now))
    cycle.planning_snapshot = [
        {**row, 'owner_clan_id': None, 'port': row['id'] == target.id, 'fortress': row['id'] == remote.id}
        for row in cycle.planning_snapshot]
    db.flush()
    data = service.planning(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id, now=now)
    assert data['attack_routes'] == [{'territory_id': land.id, 'source_id': None, 'route': 'land'}]
    cycle.planning_snapshot = [{**row, 'owner_clan_id': ally.id if row['id'] == land.id else None} for row in cycle.planning_snapshot]
    db.flush()
    assert service.planning(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id, now=now)['attack_routes'] == []


def test_planning_exposes_port_route_without_requiring_adjacency(db):
    users, clan, land, _, remote, cycle, service, now = prepared(db)
    cycle.planning_snapshot = [{**row, 'port': row['id'] == land.id, 'coastal': row['id'] == remote.id} for row in cycle.planning_snapshot]
    db.flush()
    data = service.planning(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id, now=now)
    assert {'territory_id': remote.id, 'source_id': land.id, 'route': 'sea'} in data['attack_routes']
    users[0].onboarding_completed_at = None
    db.flush()
    assert not service.planning(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id, now=now)['editable']


def test_frozen_context_keeps_reserve_capacity_when_clan_level_falls(db):
    users, clan, _, _, _, cycle, service, now = prepared(db)
    service.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
                 expected_revision=0, orders=[Order(users[0].id, 'reserve'), Order(users[1].id, 'reserve')], now=now)
    reveal = CampaignCycleStore.timeline(cycle).battle_at
    service.freeze(db, cycle_id=cycle.id, now=reveal)
    clan.level = 1
    db.flush()
    data = service.planning(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id, now=reveal)
    assert data['limits']['reserves'] == 2
    assert len(data['plan']['orders']) == 2
