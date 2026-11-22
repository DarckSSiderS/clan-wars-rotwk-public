import copy
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCyclePlan, CampaignCycleRecord
from app.models.clan import Clan, ClanMember, ClanMembershipPeriod
from app.models.cycle_battle import CycleTerritoryBattle
from app.models.cycle_reinforcement_state import CycleReinforcementState
from app.models.external_identity import ExternalPlayerIdentity
from app.models.territory import Territory
from app.models.user import User
from app.services.campaign_cycle_store import CycleConflict
from app.services.cycle_battle_service import CycleBattleService
from app.services.cycle_reinforcement_store import CycleReinforcementStore, encode_state, decode_state
from app.services import cycle_reinforcements as rules


T = datetime(2026, 10, 15, tzinfo=timezone.utc)


@pytest.fixture
def world(db):
    users = [User(username=f'rs{i}', hashed_password='unused', onboarding_completed_at=T) for i in range(8)]
    db.add_all(users)
    db.flush()
    clans = [Clan(name=f'Reinforcement {i}', leader_id=users[n].id, level=3)
             for i, n in enumerate((0, 3, 5))]
    db.add_all(clans)
    db.flush()
    for clan, indexes in zip(clans, ((0, 1, 2), (3, 4), (5, 6))):
        for n in indexes:
            db.add(ClanMember(clan_id=clan.id, user_id=users[n].id,
                              joined_at=T - timedelta(days=20), is_warlord=n == 2))
    for n, user in enumerate(users):
        db.add(ExternalPlayerIdentity(user_id=user.id, source='bfmeladder',
               external_uuid=str(UUID(int=n + 1)), current_nickname=user.username,
               verification_status='verified'))
    land = Territory(name='Reserve test', region='Local', svg_path_data='M0 0',
                     owner_clan_id=clans[1].id, is_playable=True)
    season = CampaignSeason(number=1, name='Reserve season', starts_at=T - timedelta(hours=96),
                            rules_snapshot={'mechanics_version': 'cycle_v1', 'version': 2})
    db.add_all((land, season))
    db.flush()
    cycle = CampaignCycleRecord(season_id=season.id, number=5, rule_version=2,
        starts_at=T - timedelta(hours=96), preparation_at=T - timedelta(hours=24),
        orders_frozen_at=T, planning_snapshot=[{'id': land.id, 'owner_clan_id': clans[1].id}],
        dependencies={})
    db.add(cycle)
    db.flush()
    orders = (({'user_id': users[1].id, 'kind': 'reserve', 'territory_id': None},
               {'user_id': users[2].id, 'kind': 'reserve', 'territory_id': None}),
              ({'user_id': users[3].id, 'kind': 'defend', 'territory_id': land.id},),
              ({'user_id': users[5].id, 'kind': 'attack', 'territory_id': land.id},
               {'user_id': users[6].id, 'kind': 'ambush', 'territory_id': land.id}))
    for clan, indexes, commands in zip(clans, ((0, 1, 2), (3, 4), (5, 6)), orders):
        db.add(CampaignCyclePlan(cycle_id=cycle.id, clan_id=clan.id, orders=list(commands),
            frozen_at=T, snapshot={'level': 3, 'member_ids': [users[i].id for i in indexes],
            'allied_clan_ids': [clans[1 if clan == clans[0] else 0].id] if clan != clans[2] else []}))
    db.flush()
    CycleBattleService().create_from_orders(db, cycle_id=cycle.id)
    return users, clans, land, cycle


def initialize(db, world):
    return CycleReinforcementStore().initialize(db, cycle_id=world[3].id)


def request(db, world, *, command='q', now=T, revision=None, actor=None):
    users, clans, land, cycle = world
    return CycleReinforcementStore().request_help(db, cycle_id=cycle.id, request_id=command,
        clan_id=clans[1].id, territory_id=land.id, actor_user_id=actor or users[3].id,
        now=now, expected_revision=revision)


def send(db, world, *, command='d', request_id='q', indexes=(1,), now=T, revision=None, actor=None,
         origin_territory_id=None):
    users, clans, land, cycle = world
    return CycleReinforcementStore().dispatch(db, cycle_id=cycle.id, dispatch_id=command,
        sender_clan_id=clans[0].id, recipient_clan_id=clans[1].id, territory_id=land.id,
        player_user_ids=[users[i].id for i in indexes], actor_user_id=actor or users[0].id,
        request_id=request_id, now=now, expected_revision=revision, origin_territory_id=origin_territory_id)


def test_initialization_verified_uuid_frozen_level_and_reload(db, world):
    world[1][0].level = 1
    row = initialize(db, world)
    assert row.revision == 1
    assert initialize(db, world).id == row.id
    state = decode_state(row.payload['state'])
    assert state.reserves[0].capacity == 3
    assert state.reserves[0].players[0] == rules.PlayerIdentity('bfmeladder', UUID(int=2))
    assert decode_state(json.loads(json.dumps(encode_state(state)))) == state
    db.expire_all()
    assert decode_state(db.get(CycleReinforcementState, row.id).payload['state']) == state


@pytest.mark.parametrize('corruption', ['unverified', 'invalid_uuid', 'missing_roster', 'missing_battle', 'unfrozen'])
def test_initialization_fails_closed(db, world, corruption):
    users, clans, _, cycle = world
    identity = db.query(ExternalPlayerIdentity).filter_by(user_id=users[1].id).one()
    if corruption == 'unverified':
        identity.verification_status = 'unverified'
    elif corruption == 'invalid_uuid':
        identity.external_uuid = 'uuid-1'
    elif corruption == 'missing_roster':
        plan = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle.id, clan_id=clans[0].id).one()
        plan.snapshot = {**plan.snapshot, 'member_ids': []}
    elif corruption == 'missing_battle':
        db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle.id).delete()
    else:
        cycle.orders_frozen_at = None
    db.flush()
    with pytest.raises(ValueError):
        initialize(db, world)
    assert db.query(CycleReinforcementState).count() == 0


def test_permissions_and_private_projection_membership(db, world):
    initialize(db, world)
    with pytest.raises(PermissionError):
        request(db, world, actor=world[0][4].id)
    with pytest.raises(PermissionError):
        send(db, world, actor=world[0][1].id)
    service = CycleReinforcementStore()
    public = service.read(db, cycle_id=world[3].id)
    assert public['reserves'] == [] and public['ambushes'] == []
    with pytest.raises(PermissionError):
        service.read(db, cycle_id=world[3].id, viewer_clan_id=world[1][2].id,
                     actor_user_id=world[0][0].id)
    own = service.read(db, cycle_id=world[3].id, viewer_clan_id=world[1][2].id,
                       actor_user_id=world[0][5].id)
    assert len(own['ambushes']) == 1
    assert all(r['clan_id'] == world[1][2].id for r in own['reserves'])
    assert 'state' not in own and 'bindings' not in own and 'reserve_history' not in own


@pytest.mark.parametrize('offset', [-1, 86400])
def test_new_commands_reject_outside_first_day(db, world, offset):
    initialize(db, world)
    with pytest.raises(ValueError):
        request(db, world, now=T + timedelta(seconds=offset))
    request(db, world)
    with pytest.raises(ValueError):
        send(db, world, now=T + timedelta(seconds=offset))


def test_atomic_first_success_dependency_and_stable_retry(db, world):
    initialize(db, world)
    first = request(db, world)
    request_revision = first.revision
    row = send(db, world, revision=request_revision)
    revision = row.revision
    assert request(db, world, now=T + timedelta(days=2), revision=1).revision == revision
    assert send(db, world, now=T + timedelta(days=2), revision=1).revision == revision
    assert world[3].dependencies['interception:d'] is False
    with pytest.raises(ValueError):
        send(db, world, indexes=(2,))
    with pytest.raises(ValueError):
        send(db, world, command='loser', indexes=(2,))
    assert decode_state(row.payload['state']).requests[0].dispatch_id == 'd'
    assert len(decode_state(row.payload['state']).dispatches) == 1
    public = CycleReinforcementStore().read(db, cycle_id=world[3].id)
    assert len(public['ambushes']) == 1 and public['reserves'] == []


def test_stale_revision_does_not_consume_players_or_request(db, world):
    initialize(db, world)
    request(db, world)
    with pytest.raises(CycleConflict):
        send(db, world, revision=1)
    send(db, world, actor=world[0][2].id)


@pytest.mark.parametrize('exit_kind', ['removed', 'rejoined', 'period_exit'])
def test_dispatch_db_roster_checks_even_for_frozen_reserve(db, world, exit_kind):
    initialize(db, world)
    request(db, world)
    users, clans, _, _ = world
    member = db.query(ClanMember).filter_by(user_id=users[1].id, clan_id=clans[0].id).one()
    if exit_kind == 'removed':
        db.delete(member)
    elif exit_kind == 'rejoined':
        member.joined_at = T + timedelta(minutes=1)
    else:
        db.add(ClanMembershipPeriod(user_id=users[1].id, clan_id=clans[0].id,
            started_at=T - timedelta(days=2), ended_at=T + timedelta(minutes=1)))
    db.flush()
    with pytest.raises(ValueError):
        send(db, world, now=T + timedelta(hours=1))
    state = decode_state(db.query(CycleReinforcementState).one().payload['state'])
    assert not state.dispatches and state.requests[0].dispatch_id is None


def test_frozen_alliances_not_live_and_retry_after_nickname_change(db, world):
    initialize(db, world)
    request(db, world)
    for plan in db.query(CampaignCyclePlan).filter_by(cycle_id=world[3].id):
        plan.snapshot = {**plan.snapshot, 'allied_clan_ids': []}
    row = send(db, world)
    identity = db.query(ExternalPlayerIdentity).filter_by(user_id=world[0][1].id).one()
    identity.current_nickname = 'renamed'
    db.flush()
    assert send(db, world, now=T + timedelta(hours=2)).revision == row.revision


def test_trusted_resolution_waits_loading_completes_dependency_once(db, world):
    initialize(db, world)
    request(db, world)
    row = send(db, world)
    store = CycleReinforcementStore()
    kwargs = dict(cycle_id=world[3].id, dispatch_id='d', help_score=Decimal('12.125'),
                  ambush_scores={world[1][2].id: Decimal('12.125')})
    with pytest.raises(ValueError):
        store._resolve_interception(db, now=T + timedelta(hours=14, minutes=4), **kwargs)
    result = store._resolve_interception(db, now=T + timedelta(hours=14, minutes=5), **kwargs)
    revision = result.revision
    db.expire_all()
    assert store._resolve_interception(db, now=T + timedelta(hours=15), **kwargs).revision == revision
    assert db.get(CampaignCycleRecord, world[3].id).dependencies['interception:d'] is True
    state = decode_state(result.payload['state'])
    assert state.dispatches[0].outcome == rules.Outcome.EXHAUSTED
    assert state.dispatches[0].help_score == Decimal('12.125')
    assert state.territory_factor('d', T + timedelta(hours=24)) == Decimal('0.5')
    assert not hasattr(store, 'resolve')


def test_caller_rollback_removes_state_and_dependency(db, world):
    db.commit()  # Fixture only; the adapter must never commit.
    initialize(db, world)
    request(db, world)
    send(db, world)
    cycle_id = world[3].id
    db.rollback()
    assert db.query(CycleReinforcementState).count() == 0
    assert 'interception:d' not in db.get(CampaignCycleRecord, cycle_id).dependencies


def test_unique_cycle_state(db, world):
    row = initialize(db, world)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(CycleReinforcementState(cycle_id=row.cycle_id, payload=row.payload, revision=1))
        db.flush()


@pytest.mark.parametrize('bad', [None, {}, {'schema': 99}, {'__type__': 'os.system', 'fields': {}},
                               {'schema': 1, 'aggregate': 'pickle-data'}])
def test_decode_rejects_untyped_or_unknown_payload(bad):
    with pytest.raises(ValueError):
        decode_state(bad)


@pytest.mark.parametrize('delta,other_season,blocked', [(1, False, True), (2, False, True),
                                                     (3, False, False), (1, True, False)])
def test_prior_frozen_plans_block_reserve_across_clan_change(db, world, delta, other_season, blocked):
    users, clans, _, cycle = world
    season_id = cycle.season_id
    if other_season:
        season = CampaignSeason(number=2, name='Prior', starts_at=T - timedelta(days=50), status='completed')
        db.add(season)
        db.flush()
        season_id = season.id
    prior = CampaignCycleRecord(season_id=season_id, number=cycle.number - delta, rule_version=2,
        starts_at=T - timedelta(days=30), preparation_at=T - timedelta(days=26),
        orders_frozen_at=T - timedelta(days=25), dependencies={})
    db.add(prior)
    db.flush()
    db.add(CampaignCyclePlan(cycle_id=prior.id, clan_id=clans[2].id,
        frozen_at=T - timedelta(days=25), orders=[{'user_id': users[1].id, 'kind': 'reserve'}],
        snapshot={'level': 3, 'member_ids': [users[1].id], 'allied_clan_ids': []}))
    db.flush()
    if blocked:
        with pytest.raises(ValueError, match='N\\+3'):
            initialize(db, world)
    else:
        assert initialize(db, world)


def test_frozen_roster_cannot_claim_someone_elses_db_member(db, world):
    users, clans, _, cycle = world
    member = db.query(ClanMember).filter_by(user_id=users[1].id).one()
    member.clan_id = clans[2].id
    db.flush()
    with pytest.raises(ValueError, match='membership'):
        initialize(db, world)


def test_initialization_preserves_departed_reserve_with_membership_history(db, world):
    users, clans, _, _ = world
    member = db.query(ClanMember).filter_by(user_id=users[1].id).one()
    db.add(ClanMembershipPeriod(user_id=users[1].id, clan_id=clans[0].id,
        started_at=T - timedelta(days=2), ended_at=T + timedelta(minutes=1)))
    db.delete(member)
    db.flush()
    row = initialize(db, world)
    assert rules.PlayerIdentity('bfmeladder', UUID(int=2)) in decode_state(row.payload['state']).reserves[0].players
    request(db, world)
    with pytest.raises(ValueError):
        send(db, world, now=T + timedelta(hours=1))


def test_new_dispatch_rechecks_verified_identity_but_retry_uses_frozen_binding(db, world):
    initialize(db, world)
    request(db, world)
    identity = db.query(ExternalPlayerIdentity).filter_by(user_id=world[0][1].id).one()
    identity.verification_status = 'unverified'
    db.flush()
    with pytest.raises(ValueError):
        send(db, world)
    identity.verification_status = 'verified'
    db.flush()
    sent = send(db, world)
    identity.verification_status = 'unverified'
    db.flush()
    assert send(db, world, now=T + timedelta(hours=2)).revision == sent.revision


def test_sql_cas_rejects_stale_loaded_row(db, world):
    initialize(db, world)
    store = CycleReinforcementStore()
    with db.begin_nested():
        cycle, row, state, _ = store._locked(db, world[3].id)
        revision = row.revision
        # Simulate another writer between the read and the conditional UPDATE.
        db.query(CycleReinforcementState).filter_by(id=row.id).update(
            {'revision': revision + 1}, synchronize_session=False)
        with pytest.raises(CycleConflict, match='Concurrent'):
            store._write(db, cycle, row,
                state.request_help('q', world[1][1].id, world[2].id, T), revision)


def test_codec_rejects_unknown_fields_and_untyped_nested_uuid(db, world):
    row = initialize(db, world)
    payload = copy.deepcopy(row.payload['state'])
    payload['aggregate']['fields']['surprise'] = 1
    with pytest.raises(ValueError):
        decode_state(payload)
    payload = copy.deepcopy(row.payload['state'])
    player = payload['aggregate']['fields']['reserves']['items'][0]['fields']['players']['items'][0]
    player['fields']['uuid'] = str(UUID(int=2))
    with pytest.raises(ValueError):
        decode_state(payload)


def freeze_identity_maps(db, cycle_id):
    for plan in db.query(CampaignCyclePlan).filter_by(cycle_id=cycle_id):
        plan.snapshot = {**plan.snapshot, 'player_identities': {
            str(uid): {'source': 'bfmeladder', 'uuid': str(UUID(int=uid))}
            for uid in plan.snapshot['member_ids']}}
    db.flush()


def test_initialization_uses_frozen_identities_for_every_assignment(db, world):
    freeze_identity_maps(db, world[3].id)
    for identity in db.query(ExternalPlayerIdentity):
        identity.external_uuid = str(UUID(int=identity.user_id + 100))
        identity.verification_status = 'unverified'
    db.flush()
    row = initialize(db, world)
    state = decode_state(row.payload['state'])
    expected = lambda n: rules.PlayerIdentity('bfmeladder', UUID(int=world[0][n].id))
    assert state.reserves[0].players == (expected(1), expected(2))
    assert state.ambushes[0].players == (expected(6),)
    assert set(state.battles[0].ordinary_players) == {expected(3), expected(5)}


@pytest.mark.parametrize('bad', [{}, None, {'source': 'bfmeladder', 'uuid': 'not-a-uuid'}])
def test_present_but_incomplete_or_invalid_frozen_map_never_falls_back(db, world, bad):
    freeze_identity_maps(db, world[3].id)
    plan = db.query(CampaignCyclePlan).filter_by(cycle_id=world[3].id, clan_id=world[1][0].id).one()
    mapping = dict(plan.snapshot['player_identities'])
    mapping[str(world[0][1].id)] = bad
    plan.snapshot = {**plan.snapshot, 'player_identities': mapping}
    db.flush()
    with pytest.raises(ValueError):
        initialize(db, world)


def test_prior_plan_frozen_uuid_blocks_new_internal_account(db, world):
    users, clans, _, cycle = world
    freeze_identity_maps(db, cycle.id)
    prior = CampaignCycleRecord(season_id=cycle.season_id, number=4, rule_version=2,
        starts_at=T - timedelta(days=30), preparation_at=T - timedelta(days=26),
        orders_frozen_at=T - timedelta(days=25), dependencies={})
    db.add(prior)
    db.flush()
    # Historical internal account differs; only the frozen UUID links them.
    db.add(CampaignCyclePlan(cycle_id=prior.id, clan_id=clans[2].id,
        frozen_at=T - timedelta(days=25), orders=[{'user_id': users[7].id, 'kind': 'reserve'}],
        snapshot={'level': 3, 'member_ids': [users[7].id], 'allied_clan_ids': [],
                  'player_identities': {str(users[7].id): {'source': 'bfmeladder',
                                                        'uuid': str(UUID(int=users[1].id))}}}))
    db.flush()
    with pytest.raises(ValueError, match='N\\+3'):
        initialize(db, world)
