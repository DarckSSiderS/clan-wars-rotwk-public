"""R10: durable, private defence fallback; all databases are disposable SQLite."""
from datetime import timedelta

import pytest

from app.models.campaign_cycle import CampaignCyclePlan, CampaignCycleRecord, CycleScoutRequest
from app.models.clan import ClanMember
from app.models.external_identity import ExternalPlayerIdentity
from app.models.territory import Territory
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict
from app.services.cycle_orders import Order, PlanningContext, TerritoryState, fill_defence_template
from app.services.cycle_plan_service import CyclePlanService
from tests.test_cycle_plan_service import setup_world
from tests.test_cycle_operations_api import client_for, path, no_network  # noqa: F401


def prepared(db):
    users, clan, land, cycle = setup_world(db)
    service = CyclePlanService()
    timeline = CampaignCycleStore.timeline(cycle)
    service.capture_preparation(db, cycle_id=cycle.id, now=timeline.preparation_at)
    return users, clan, land, cycle, service, timeline


def save_template(db, world, assignments=None, revision=0, actor=0, now=None):
    users, clan, land, cycle, service, timeline = world
    return service.save_defence_template(db, cycle_id=cycle.id, clan_id=clan.id,
        actor_user_id=users[actor].id, expected_revision=revision,
        assignments=assignments if assignments is not None else [dict(user_id=users[2].id, territory_id=land.id)],
        now=now or timeline.preparation_at)


def test_pure_fallback_skips_scout_and_preserves_manual_assignments():
    context = PlanningContext(1, 2, 0, frozenset({1, 2, 3}), frozenset(),
        (TerritoryState(10, 1),), scouting_ids=frozenset({2}))
    result = fill_defence_template([Order(1, 'reserve')], {1: 10, 2: 10, 3: 10}, context)
    assert result == (Order(1, 'reserve'), Order(3, 'defend', 10))


def test_template_persists_by_season_clan_and_is_not_a_manual_plan(db):
    world = prepared(db)
    users, clan, land, cycle, service, timeline = world
    saved = save_template(db, world)
    assert saved['revision'] == 1
    assert saved['assignments'] == [dict(user_id=users[2].id, territory_id=land.id)]
    assert db.query(CampaignCyclePlan).count() == 0
    users[2].display_name = 'Renamed'
    db.flush()
    data = service.planning(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
                            now=timeline.preparation_at)
    assert data['defence_template']['revision'] == 1
    assert data['defence_template']['editable']
    assert data['defence_template']['editable_until'] == timeline.battle_at
    assert data['defence_template']['fallback_orders'] == [dict(user_id=users[2].id, kind='defend',
        territory_id=land.id, source_id=None, route='land')]
    following = CampaignCycleRecord(season_id=cycle.season_id, number=2, rule_version=2,
        starts_at=timeline.replay_deadline + timedelta(hours=12),
        preparation_at=timeline.replay_deadline + timedelta(hours=12), dependencies={})
    db.add(following); db.flush()
    assert service.read_defence_template(db, cycle_id=following.id, clan_id=clan.id,
        actor_user_id=users[0].id, now=CampaignCycleStore.timeline(following).preparation_at)['revision'] == 1
    from app.models.campaign import CampaignSeason
    db.get(CampaignSeason, cycle.season_id).status = 'completed'
    db.flush()
    other_season = CampaignSeason(number=2, name='Next', status='active', starts_at=timeline.starts_at,
        rules_snapshot={'version': 2, 'mechanics_version': 'cycle_v1'})
    db.add(other_season); db.flush()
    other = CampaignCycleStore().start(db, season_id=other_season.id)
    assert service.read_defence_template(db, cycle_id=other.id, clan_id=clan.id,
        actor_user_id=users[0].id, now=CampaignCycleStore.timeline(other).preparation_at)['revision'] == 0


def test_template_freeze_without_plan_snapshots_identities_and_is_idempotent(db):
    world = prepared(db)
    users, clan, land, cycle, service, timeline = world
    save_template(db, world)
    service.freeze(db, cycle_id=cycle.id, now=timeline.battle_at)
    plan = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle.id, clan_id=clan.id).one()
    assert plan.orders == [dict(user_id=users[2].id, kind='defend', territory_id=land.id, source_id=None, route='land')]
    assert plan.snapshot['player_identities'][str(users[2].id)]['uuid'] == f'uuid-{users[2].id}'
    assert plan.snapshot['defence_template']['revision'] == 1
    view = service.planning(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
                            now=timeline.battle_at)
    assert view['defence_template']['fallback_orders'] == []
    orders, snapshot = list(plan.orders), dict(plan.snapshot)
    service.freeze(db, cycle_id=cycle.id, now=timeline.battle_at + timedelta(minutes=1))
    assert plan.orders == orders and plan.snapshot == snapshot


@pytest.mark.parametrize('kind', ['attack', 'defend', 'reserve', 'ambush'])
def test_all_manual_kinds_win_over_template(db, kind):
    world = prepared(db)
    users, clan, land, cycle, service, timeline = world
    target = Territory(name='Target', region='Test', svg_path_data='M0 0', is_playable=True)
    db.add(target); db.flush()
    land.adjacent_territory_ids = [target.id]
    # Update this test's preparation snapshot before it is captured, not production semantics.
    cycle.planning_snapshot = None; db.flush()
    service.capture_preparation(db, cycle_id=cycle.id, now=timeline.preparation_at)
    manual = Order(users[2].id, kind, target.id if kind == 'attack' else None if kind == 'reserve' else land.id,
                   land.id if kind == 'attack' else None)
    orders = [Order(users[0].id, 'defend', land.id)] if kind == 'ambush' else []
    orders.append(manual)
    plan = service.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
        expected_revision=0, orders=orders, now=timeline.preparation_at)
    save_template(db, world, [dict(user_id=u.id, territory_id=land.id) for u in users[:3]])
    service.freeze(db, cycle_id=cycle.id, now=timeline.battle_at)
    assert next(o for o in plan.orders if o['user_id'] == users[2].id)['kind'] == kind
    assert len({o['user_id'] for o in plan.orders}) == len(plan.orders) == 3
    assert all(o['kind'] == 'defend' for o in plan.orders if o['user_id'] != users[2].id)


@pytest.mark.parametrize('reason', ['departed', 'lost_land', 'scout', 'unverified'])
def test_freeze_skips_invalid_fallback_with_warning_without_reassigning(db, reason):
    world = prepared(db)
    users, clan, land, cycle, service, timeline = world
    save_template(db, world)
    if reason == 'departed':
        db.query(ClanMember).filter_by(clan_id=clan.id, user_id=users[2].id).delete()
    elif reason == 'lost_land':
        land.owner_clan_id = None
    elif reason == 'unverified':
        db.query(ExternalPlayerIdentity).filter_by(user_id=users[2].id).one().verification_status = 'unverified'
    else:
        db.add(CycleScoutRequest(cycle_id=cycle.id, clan_id=clan.id, territory_id=land.id,
            scout_user_id=users[2].id, scout_uuid=f'uuid-{users[2].id}', requested_at=timeline.preparation_at))
    db.flush()
    service.freeze(db, cycle_id=cycle.id, now=timeline.battle_at)
    plan = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle.id, clan_id=clan.id).one()
    assert plan.orders == []
    assert any(w['source'] == 'defence_template' and w['user_id'] == users[2].id for w in plan.snapshot['warnings'])


def test_template_cannot_rescue_a_discarded_manual_order(db):
    world = prepared(db)
    users, clan, land, cycle, service, timeline = world
    plan = service.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
        expected_revision=0, orders=[Order(users[1].id, 'reserve'), Order(users[2].id, 'reserve')],
        now=timeline.preparation_at)
    save_template(db, world)
    clan.level = 1; db.flush()
    service.freeze(db, cycle_id=cycle.id, now=timeline.battle_at)
    assert plan.orders == []


def test_permissions_cas_clear_and_read_does_not_create_template(db):
    world = prepared(db)
    users, clan, land, cycle, service, timeline = world
    from app.models.cycle_defence_template import CycleDefenceTemplate
    assert service.read_defence_template(db, cycle_id=cycle.id, clan_id=clan.id,
        actor_user_id=users[2].id, now=timeline.preparation_at)['revision'] == 0
    assert db.query(CycleDefenceTemplate).count() == 0
    with pytest.raises(PermissionError):
        save_template(db, world, actor=2)
    save_template(db, world, actor=1)
    with pytest.raises(CycleConflict):
        save_template(db, world, revision=0)
    assert save_template(db, world, assignments=[], revision=1)['revision'] == 2
    with pytest.raises(PermissionError):
        service.read_defence_template(db, cycle_id=cycle.id, clan_id=clan.id,
            actor_user_id=users[3].id, now=timeline.preparation_at)
    assert db.query(CycleDefenceTemplate).count() == 1


@pytest.mark.parametrize('reason', ['duplicate', 'foreign_player', 'foreign_land', 'invalid_type'])
def test_template_rejects_invalid_assignments_atomically(db, reason):
    world = prepared(db)
    users, clan, land, cycle, service, timeline = world
    save_template(db, world)
    entries = [dict(user_id=users[2].id, territory_id=land.id)]
    if reason == 'duplicate': entries *= 2
    if reason == 'foreign_player': entries[0]['user_id'] = users[3].id
    if reason == 'foreign_land': entries[0]['territory_id'] = 9999
    if reason == 'invalid_type': entries[0]['user_id'] = True
    with pytest.raises(ValueError):
        save_template(db, world, entries, revision=1)
    assert service.read_defence_template(db, cycle_id=cycle.id, clan_id=clan.id,
        actor_user_id=users[0].id, now=timeline.preparation_at)['revision'] == 1


@pytest.mark.parametrize('phase', ['registration', 'battle', 'replay_loading', 'settlement', 'complete', 'scheduled'])
def test_template_edit_only_during_preparation_or_rest(db, phase):
    world = prepared(db)
    users, clan, land, cycle, service, timeline = world
    now = dict(registration=timeline.starts_at, battle=timeline.battle_at,
        replay_loading=timeline.battle_ends_at, settlement=timeline.replay_deadline,
        complete=timeline.replay_deadline + timedelta(hours=12), scheduled=timeline.starts_at - timedelta(seconds=1))[phase]
    if phase == 'complete': cycle.settled_at = timeline.replay_deadline; db.flush()
    with pytest.raises(ValueError): save_template(db, world, now=now)


def test_rest_edits_next_template_not_frozen_history_or_old_cycles(db):
    world = prepared(db)
    users, clan, land, cycle, service, timeline = world
    service.freeze(db, cycle_id=cycle.id, now=timeline.battle_at)
    cycle.settled_at = timeline.replay_deadline; db.flush()
    rest = timeline.replay_deadline + timedelta(minutes=1)
    save_template(db, world, now=rest)
    view = service.planning(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id, now=rest)
    assert view['defence_template']['editable'] and view['defence_template']['revision'] == 1
    assert view['defence_template']['editable_until'] == timeline.replay_deadline + timedelta(hours=12)
    assert view['defence_template']['fallback_orders'] == []
    plan = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle.id, clan_id=clan.id).one()
    assert plan.orders == [] and plan.snapshot['defence_template']['revision'] == 0
    # Pre-feature plans have no invented template, even after one is saved.
    plan.snapshot = {k: v for k, v in plan.snapshot.items() if k != 'defence_template'}; db.flush()
    frozen_view = service.planning(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
        now=timeline.battle_at)
    assert frozen_view['defence_template']['revision'] == 0
    assert frozen_view['defence_template']['assignments'] == []
    following = CampaignCycleRecord(season_id=cycle.season_id, number=2, rule_version=2,
        starts_at=rest + timedelta(hours=12), preparation_at=rest + timedelta(hours=12), dependencies={})
    db.add(following); db.flush()
    with pytest.raises(ValueError): save_template(db, world, revision=1, now=rest)


def test_template_http_rights_cas_validation_and_no_client_authority(db, monkeypatch):
    world = prepared(db)
    users, clan, land, cycle, service, timeline = world
    db.commit()
    client, app = client_for(db, monkeypatch, users[0], timeline.preparation_at)
    url = path(cycle, clan) + '/defence-template'
    body = dict(expected_revision=0, assignments=[dict(user_id=users[2].id, territory_id=land.id)])
    assert client.get(url).status_code == 200
    result = client.put(url, json=body)
    assert result.status_code == 200, result.text
    assert result.json()['revision'] == 1
    assert client.put(url, json=body).status_code == 409
    for invalid in [dict(body, expected_revision=True), dict(body, expected_revision=1, now='2099'),
                    dict(body, expected_revision=1, assignments=[dict(user_id=True, territory_id=land.id)])]:
        assert client.put(url, json=invalid).status_code == 409
    from app.core.auth import get_current_active_user
    app.dependency_overrides[get_current_active_user] = lambda: users[2]
    assert client.get(url).status_code == 200
    assert client.put(url, json=dict(body, expected_revision=1)).status_code == 403
    app.dependency_overrides[get_current_active_user] = lambda: users[3]
    assert client.get(url).status_code == 403
    assert client.put(url, json=dict(body, expected_revision=1)).status_code == 403


def test_sql_revision_cas_rejects_a_stale_identity_map(db):
    from sqlalchemy.orm import Session
    from app.models.cycle_defence_template import CycleDefenceTemplate
    world = prepared(db)
    save_template(db, world)
    db.commit()
    cached = db.query(CycleDefenceTemplate).one()
    assert cached.revision == 1
    with Session(bind=db.get_bind()) as other:
        other.query(CycleDefenceTemplate).filter_by(id=cached.id).update({'revision': 2})
        other.commit()
    assert cached.revision == 1
    with pytest.raises(CycleConflict):
        save_template(db, world, assignments=[], revision=1)
    db.rollback()
    assert db.query(CycleDefenceTemplate).one().revision == 2


@pytest.mark.parametrize('reason', ['closed_season', 'legacy', 'onboarding', 'revoked'])
def test_template_rechecks_server_authority(db, reason):
    from app.models.campaign import CampaignSeason
    world = prepared(db)
    users, clan, land, cycle, service, timeline = world
    if reason == 'closed_season': db.get(CampaignSeason, cycle.season_id).status = 'completed'
    if reason == 'legacy': db.get(CampaignSeason, cycle.season_id).rules_snapshot = {'mechanics_version': 'legacy'}
    if reason == 'onboarding': users[1].onboarding_completed_at = None
    if reason == 'revoked': db.query(ClanMember).filter_by(user_id=users[1].id).one().is_warlord = False
    db.flush()
    with pytest.raises((ValueError, PermissionError)):
        save_template(db, world, actor=1)
