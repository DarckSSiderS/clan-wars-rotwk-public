from datetime import timedelta

import pytest

from app.models.clan import Clan, ClanMember
from app.models.external_identity import ExternalPlayerIdentity
from app.models.territory import Territory
from app.models.user import User
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict
from app.services.cycle_orders import Order
from app.services.cycle_plan_service import CyclePlanService
from tests.test_campaign_cycle_store import season, START


def setup_world(db):
    users = [User(username=f'p{i}', email=f'p{i}@test.invalid', hashed_password='unused', is_active=True,
                  onboarding_completed_at=START) for i in range(4)]
    db.add_all(users)
    db.flush()
    clan = Clan(name='Test clan', leader_id=users[0].id, level=2, territory_points=500)
    db.add(clan)
    db.flush()
    for user in users[:3]:
        db.add(ClanMember(clan_id=clan.id, user_id=user.id, is_warlord=user == users[1], joined_at=START))
        db.add(ExternalPlayerIdentity(user_id=user.id, external_uuid=f'uuid-{user.id}', current_nickname=user.username,
                                      source='bfmeladder', verification_status='verified'))
    land = Territory(name='Home', region='Test', svg_path_data='M0 0', owner_clan_id=clan.id,
                     adjacent_territory_ids=[], is_playable=True)
    db.add(land)
    db.flush()
    cycle = CampaignCycleStore().start(db, season_id=season(db).id)
    return users, clan, land, cycle


def test_reveal_snapshots_clans_without_orders_for_uuid_opponent_checks(db):
    users, _, _, cycle = setup_world(db)
    other = Clan(name='No orders', leader_id=users[3].id, level=1)
    db.add(other)
    db.flush()
    db.add(ClanMember(clan_id=other.id, user_id=users[3].id))
    db.add(ExternalPlayerIdentity(user_id=users[3].id, source='bfmeladder', external_uuid='stable-other',
        current_nickname=users[3].username, verification_status='verified'))
    db.flush()
    service = CyclePlanService()
    timeline = CampaignCycleStore.timeline(cycle)
    service.capture_preparation(db, cycle_id=cycle.id, now=timeline.preparation_at)
    service.freeze(db, cycle_id=cycle.id, now=timeline.battle_at)
    snapshot = service.read(db, cycle_id=cycle.id, clan_id=other.id, actor_user_id=users[3].id)
    assert snapshot['frozen_at'] is not None
    assert snapshot['orders'] == []
    from app.models.campaign_cycle import CampaignCyclePlan
    row = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle.id, clan_id=other.id).one()
    assert row.snapshot['player_identities'][str(users[3].id)]['uuid'] == 'stable-other'


def test_saved_plan_uses_revision_and_permissions_and_private_read(db):
    users, clan, land, cycle = setup_world(db)
    service = CyclePlanService()
    now = CampaignCycleStore.timeline(cycle).preparation_at
    service.capture_preparation(db, cycle_id=cycle.id, now=now)
    plan = service.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
                        expected_revision=0, orders=[Order(users[2].id, 'defend', land.id)], now=now)
    assert plan.revision == 1
    assert service.read(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[2].id)['revision'] == 1
    with pytest.raises(PermissionError):
        service.read(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[3].id)
    with pytest.raises(PermissionError):
        service.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[2].id,
                     expected_revision=1, orders=[], now=now)
    with pytest.raises(CycleConflict):
        service.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[1].id,
                     expected_revision=0, orders=[], now=now)


def test_capture_is_immutable_and_plans_cannot_be_edited_after_reveal(db):
    users, clan, land, cycle = setup_world(db)
    service = CyclePlanService()
    timeline = CampaignCycleStore.timeline(cycle)
    service.capture_preparation(db, cycle_id=cycle.id, now=timeline.preparation_at)
    land.owner_clan_id = None
    db.flush()
    service.capture_preparation(db, cycle_id=cycle.id, now=timeline.preparation_at + timedelta(hours=1))
    saved = service.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
                         expected_revision=0, orders=[Order(users[2].id, 'defend', land.id)], now=timeline.preparation_at)
    service.freeze(db, cycle_id=cycle.id, now=timeline.battle_at)
    assert saved.frozen_at is not None
    with pytest.raises(ValueError):
        service.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
                     expected_revision=saved.revision, orders=[], now=timeline.battle_at)


def test_reserve_snapshot_uses_reveal_level_and_survives_later_level_drop(db):
    users, clan, land, cycle = setup_world(db)
    service = CyclePlanService()
    timeline = CampaignCycleStore.timeline(cycle)
    service.capture_preparation(db, cycle_id=cycle.id, now=timeline.preparation_at)
    saved = service.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
                         expected_revision=0, orders=[Order(users[0].id, 'reserve'), Order(users[1].id, 'reserve')],
                         now=timeline.preparation_at)
    service.freeze(db, cycle_id=cycle.id, now=timeline.battle_at)
    clan.level = 1
    db.flush()
    assert len(saved.orders) == 2
    assert saved.snapshot['level'] == 2


def test_no_new_world_snapshot_can_be_invented_after_battle_started(db):
    _, _, _, cycle = setup_world(db)
    with pytest.raises(ValueError):
        CyclePlanService().capture_preparation(db, cycle_id=cycle.id, now=CampaignCycleStore.timeline(cycle).battle_at)


def test_departed_defender_does_not_leave_an_ambush_blocking_cycle_reveal(db):
    users, clan, land, cycle = setup_world(db)
    service = CyclePlanService()
    timeline = CampaignCycleStore.timeline(cycle)
    service.capture_preparation(db, cycle_id=cycle.id, now=timeline.preparation_at)
    plan = service.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
                        expected_revision=0, orders=[Order(users[2].id, 'defend', land.id),
                                                     Order(users[1].id, 'ambush', land.id)],
                        now=timeline.preparation_at)
    db.query(ClanMember).filter_by(clan_id=clan.id, user_id=users[2].id).delete()
    db.flush()
    service.freeze(db, cycle_id=cycle.id, now=timeline.battle_at)
    assert plan.frozen_at is not None
    assert plan.orders == []
    assert plan.snapshot['warnings']


def test_reveal_freezes_active_relic_level_before_later_upgrade(db):
    users, clan, land, cycle = setup_world(db)
    from app.services.cycle_economy_store import CycleEconomyStore
    from app.models.cycle_economy import CycleEconomySnapshot
    economy = CycleEconomyStore()
    state = economy.ensure_state(db, season_id=cycle.season_id, clan_id=clan.id)
    economy.choose_starters(db, state_id=state.id, actor_id=users[0].id,
                           selected=['white_tree', 'royal_charter'], expected_revision=state.revision)
    timeline = CampaignCycleStore.timeline(cycle)
    economy.select_active(db, state_id=state.id, actor_id=users[0].id, cycle_id=cycle.id,
                          now=timeline.preparation_at, selected=['white_tree'], expected_revision=state.revision)
    plans = CyclePlanService()
    plans.capture_preparation(db, cycle_id=cycle.id, now=timeline.preparation_at)
    plans.freeze(db, cycle_id=cycle.id, now=timeline.battle_at)
    snapshot = db.query(CycleEconomySnapshot).filter_by(cycle_id=cycle.id, state_id=state.id).one()
    economy.buy_relic(db, state_id=state.id, actor_id=users[0].id, key='white_tree', expected_revision=state.revision)
    assert state.relics['white_tree'] == 2
    assert snapshot.effects[0]['level'] == 1
    assert snapshot.effects[0]['percent'] == '15'


def test_invalid_draft_reserve_after_preparation_level_drop_cannot_block_other_clans(db):
    users, clan, land, cycle = setup_world(db)
    service = CyclePlanService()
    timeline = CampaignCycleStore.timeline(cycle)
    service.capture_preparation(db, cycle_id=cycle.id, now=timeline.preparation_at)
    plan = service.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
                        expected_revision=0, orders=[Order(users[0].id, 'reserve'), Order(users[1].id, 'reserve')],
                        now=timeline.preparation_at)
    clan.level = 1
    db.flush()
    service.freeze(db, cycle_id=cycle.id, now=timeline.battle_at)
    assert cycle.orders_frozen_at is not None
    assert plan.orders == []
    assert any(w['reason'] == 'draft_reserve_exceeds_reveal_capacity' for w in plan.snapshot['warnings'])


def test_reserve_cooldown_follows_source_uuid_if_account_link_is_repaired(db):
    users, clan, land, cycle = setup_world(db)
    service = CyclePlanService()
    timeline = CampaignCycleStore.timeline(cycle)
    service.capture_preparation(db, cycle_id=cycle.id, now=timeline.preparation_at)
    service.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
                 expected_revision=0, orders=[Order(users[2].id, 'reserve')], now=timeline.preparation_at)
    service.freeze(db, cycle_id=cycle.id, now=timeline.battle_at)
    identity = db.query(ExternalPlayerIdentity).filter_by(user_id=users[2].id).one()
    identity.user_id = users[3].id
    identity.current_nickname = 'Renamed player'
    member = db.query(ClanMember).filter_by(clan_id=clan.id, user_id=users[2].id).one()
    member.user_id = users[3].id
    from app.models.campaign_cycle import CampaignCycleRecord
    following = CampaignCycleRecord(season_id=cycle.season_id, number=2, rule_version=2,
        starts_at=timeline.battle_ends_at + timedelta(hours=12),
        preparation_at=timeline.battle_ends_at + timedelta(hours=12), dependencies={})
    db.add(following)
    db.flush()
    now = CampaignCycleStore.timeline(following).preparation_at
    service.capture_preparation(db, cycle_id=following.id, now=now)
    context = service.planning(db, cycle_id=following.id, clan_id=clan.id, actor_user_id=users[0].id, now=now)
    assert next(m for m in context['members'] if m['user_id'] == users[3].id)['reserve_blocked']
    with pytest.raises(ValueError, match='cooldown'):
        service.save(db, cycle_id=following.id, clan_id=clan.id, actor_user_id=users[0].id,
                     expected_revision=0, orders=[Order(users[3].id, 'reserve')], now=now)
