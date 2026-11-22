from datetime import timedelta

import pytest

from app.models.external_identity import ExternalPlayerIdentity
from app.models.campaign_cycle import CycleScoutRequest
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_plan_service import CyclePlanService
from app.services.cycle_orders import Order
from app.services.cycle_reconnaissance_service import CycleReconnaissanceService
from tests.test_cycle_plan_service import setup_world
from tests.test_cycle_reinforcement_store import world  # noqa: F401


def prepared(db):
    users, clan, land, cycle = setup_world(db)
    now = CampaignCycleStore.timeline(cycle).preparation_at
    CyclePlanService().capture_preparation(db, cycle_id=cycle.id, now=now)
    wallet = CycleEconomyStore().ensure_state(db, season_id=cycle.season_id, clan_id=clan.id)
    return users, clan, land, cycle, now, wallet


def request(db, users, clan, land, cycle, now, wallet, player=2):
    return CycleReconnaissanceService().request(db, cycle_id=cycle.id, clan_id=clan.id,
        territory_id=land.id, scout_user_id=users[player].id, actor_user_id=users[0].id,
        expected_revision=wallet.revision, now=now)


def test_scout_is_free_verified_uuid_bound_and_locked_after_report(db):
    users, clan, land, cycle, now, wallet = prepared(db)
    row = request(db, users, clan, land, cycle, now, wallet)
    assert row.scout_user_id == users[2].id and row.scout_uuid == f'uuid-{users[2].id}'
    assert CycleEconomyStore.balance(wallet).gold == 800
    users[2].display_name = 'New nickname'
    CycleReconnaissanceService().report(db, request_id=row.id, actor_user_id=users[0].id,
        now=CampaignCycleStore.timeline(cycle).battle_at - timedelta(hours=6))
    plan = CyclePlanService().planning(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id, now=now)
    member = next(p for p in plan['members'] if p['user_id'] == users[2].id)
    assert member['scouting'] and not member['eligible'] and member['name'] == 'New nickname'
    for kind in ('attack', 'defend', 'reserve', 'ambush'):
        with pytest.raises(ValueError):
            CyclePlanService().save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
                expected_revision=0, orders=[Order(users[2].id, kind, None if kind == 'reserve' else land.id)], now=now)
    with pytest.raises(ValueError, match='changed'):
        request(db, users, clan, land, cycle, now, wallet, player=1)
    again = request(db, users, clan, land, cycle, now, wallet)
    assert again.id == row.id and CycleEconomyStore.balance(wallet).gold == 800


@pytest.mark.parametrize('kind', ['defend', 'reserve', 'ambush'])
def test_assigned_player_cannot_be_paid_scout(db, kind):
    users, clan, land, cycle, now, wallet = prepared(db)
    orders = [Order(users[1].id, 'defend', land.id)] if kind == 'ambush' else []
    orders.append(Order(users[2].id, kind, None if kind == 'reserve' else land.id))
    CyclePlanService().save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
        expected_revision=0, orders=orders, now=now)
    with pytest.raises(ValueError, match='free'):
        request(db, users, clan, land, cycle, now, wallet)
    assert CycleEconomyStore.balance(wallet).gold == 1000
    assert db.query(CycleScoutRequest).count() == 0


@pytest.mark.parametrize('invalid', ['foreign', 'unverified', 'inactive'])
def test_scout_rejects_invalid_member_without_charge(db, invalid):
    users, clan, land, cycle, now, wallet = prepared(db)
    if invalid == 'unverified':
        db.query(ExternalPlayerIdentity).filter_by(user_id=users[2].id).one().verification_status = 'unverified'
    if invalid == 'inactive':
        users[2].is_active = False
    db.flush()
    with pytest.raises(ValueError):
        request(db, users, clan, land, cycle, now, wallet, player=3 if invalid == 'foreign' else 2)
    assert CycleEconomyStore.balance(wallet).gold == 1000


def test_scout_uuid_stays_blocked_when_identity_is_rebound_and_releases_next_cycle(db):
    users, clan, land, cycle, now, wallet = prepared(db)
    row = request(db, users, clan, land, cycle, now, wallet)
    identity = db.query(ExternalPlayerIdentity).filter_by(user_id=users[2].id).one()
    db.query(ExternalPlayerIdentity).filter(ExternalPlayerIdentity.user_id == users[1].id,
        ExternalPlayerIdentity.id != identity.id).delete()
    db.flush()
    identity.user_id = users[1].id
    db.flush()
    assert {users[1].id, users[2].id} <= CyclePlanService.scouting_user_ids(db, cycle.id)
    assert not CyclePlanService.scouting_user_ids(db, cycle.id + 1)


def test_scout_cannot_dispatch_even_if_old_reserve_snapshot_contains_player(db, world):
    from tests.test_cycle_reinforcement_store import initialize, request as help_request, send, T
    users, clans, land, cycle = world
    initialize(db, world)
    help_request(db, world)
    identity = db.query(ExternalPlayerIdentity).filter_by(user_id=users[1].id).one()
    db.add(CycleScoutRequest(cycle_id=cycle.id, clan_id=clans[0].id, territory_id=land.id,
        actor_user_id=users[0].id, scout_user_id=users[1].id, scout_uuid=identity.external_uuid, requested_at=T))
    db.flush()
    with pytest.raises(ValueError, match='scout'):
        send(db, world)


def test_preparation_only_lists_free_players_and_api_requires_selection(db, monkeypatch):
    from tests.test_cycle_operations_api import client_for, path
    users, clan, land, cycle, now, wallet = prepared(db)
    CyclePlanService().save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
        expected_revision=0, orders=[Order(users[1].id, 'reserve')], now=now)
    db.commit()
    client, _ = client_for(db, monkeypatch, users[0], now)
    base = path(cycle, clan)
    prep = client.get(base + '/preparation').json()
    assert {p['user_id'] for p in prep['scout']['players']} == {users[0].id, users[2].id}
    body = {'territory_id': land.id, 'expected_revision': wallet.revision}
    assert client.post(base + '/scout', json=body).status_code == 409
    assert client.post(base + '/scout', json={**body, 'scout_user_id': users[1].id}).status_code == 409
    response = client.post(base + '/scout', json={**body, 'scout_user_id': users[2].id})
    assert response.status_code == 200, response.text
    assert response.json()['scout_uuid'] == f'uuid-{users[2].id}'
    after = client.get(base + '/preparation').json()
    assert not after['scout']['can_request']
    assert after['scout']['request']['scout_user_id'] == users[2].id


def test_planning_explains_unreachable_and_reachable_lands_without_changing_rules(db):
    from app.models.territory import Territory
    users, clan, land, cycle = setup_world(db)
    near = Territory(name='Reachable', region='Test', svg_path_data='M0 0')
    far = Territory(name='Distant', region='Test', svg_path_data='M0 0')
    fortress = Territory(name='Fortress', region='Test', svg_path_data='M0 0', stronghold_power=3, required_territories=5)
    db.add_all([near, far, fortress]); db.flush()
    land.adjacent_territory_ids = [near.id, fortress.id]
    now = CampaignCycleStore.timeline(cycle).preparation_at
    service = CyclePlanService()
    service.capture_preparation(db, cycle_id=cycle.id, now=now)
    data = service.planning(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id, now=now)
    reasons = {r['territory_id']: r['reason'] for r in data['attack_unavailable']}
    assert {r['territory_id'] for r in data['attack_routes']} == {near.id}
    assert reasons[land.id] == 'owned' and reasons[far.id] == 'no_adjacent_land_or_port'
    assert reasons[fortress.id] == 'fortress_requirements'


def test_scout_keeps_frozen_clan_identity_without_receiving_a_combat_assignment(db):
    from app.models.campaign_cycle import CampaignCyclePlan
    users, clan, land, cycle, now, wallet = prepared(db)
    request(db, users, clan, land, cycle, now, wallet)
    CyclePlanService().freeze(db, cycle_id=cycle.id, now=CampaignCycleStore.timeline(cycle).battle_at)
    frozen=db.query(CampaignCyclePlan).filter_by(cycle_id=cycle.id, clan_id=clan.id).one()
    assert users[2].id in frozen.snapshot['member_ids']
    assert frozen.snapshot['player_identities'][str(users[2].id)]['uuid'] == f'uuid-{users[2].id}'
    assert not any(o['user_id']==users[2].id for o in frozen.orders)
