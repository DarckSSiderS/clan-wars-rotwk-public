from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.models.clan import ClanMember, ClanMembershipPeriod
from app.models.cycle_battle import CycleMatchContribution
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_match_service import CycleMatchService, ReplayFacts, ReplayPlayer
from tests.test_cycle_match_service import match_world
from tests.test_cycle_reinforcement_store import world, initialize, request, send, T


def end_and_return(db, uid, clan_id, *, anchor, ended, returned=None):
    db.add(ClanMembershipPeriod(user_id=uid, clan_id=clan_id,
        started_at=anchor - timedelta(days=2), ended_at=ended))
    member = db.query(ClanMember).filter_by(user_id=uid).one()
    if returned is None:
        db.delete(member)
    else:
        db.add(ClanMembershipPeriod(user_id=uid, clan_id=clan_id, started_at=returned))
        member.joined_at = returned
    db.flush()


@pytest.mark.parametrize(('seconds_after_start', 'counted'), [(-1, False), (0, False), (1, True)])
def test_ordinary_membership_uses_game_start_with_exclusive_exit(db, seconds_after_start, counted):
    users, home, away, cycle, battle, replay = match_world(db)
    end_and_return(db, users[2].id, home.id,
        anchor=CampaignCycleStore.timeline(cycle).battle_at,
        ended=replay.started_at + timedelta(seconds=seconds_after_start))
    rows = CycleMatchService().process(db, battle_id=battle.id, replay=replay)
    departed = next(row for row in rows if row.user_id == users[2].id)
    enemy = next(row for row in rows if row.user_id == users[3].id)
    assert departed.counted is counted
    assert departed.reason == ('counted' if counted else 'membership_changed')
    assert departed.points == (Decimal(-100) if counted else 0)
    assert enemy.points == (Decimal(200) if counted else Decimal(100))


def test_same_cycle_rejoin_and_rename_cannot_restore_ordinary_assignment(db):
    users, home, _, cycle, battle, replay = match_world(db)
    anchor = CampaignCycleStore.timeline(cycle).battle_at
    end_and_return(db, users[2].id, home.id, anchor=anchor,
        ended=anchor + timedelta(minutes=2), returned=anchor + timedelta(minutes=3))
    users[2].username = 'Returned under another name'
    rows = CycleMatchService().process(db, battle_id=battle.id, replay=replay)
    departed = next(row for row in rows if row.user_id == users[2].id)
    assert not departed.counted and departed.reason == 'membership_changed'
    assert next(row for row in rows if row.user_id == users[3].id).points == 100


def test_existing_earned_points_survive_later_exit(db):
    users, home, _, cycle, battle, replay = match_world(db)
    anchor = CampaignCycleStore.timeline(cycle).battle_at
    end_and_return(db, users[2].id, home.id, anchor=anchor,
        ended=replay.finished_at + timedelta(minutes=1))
    before = CycleMatchService().process(db, battle_id=battle.id, replay=replay)
    scores = {row.id: row.points for row in before}
    later = replace(replay, replay_id='after-exit', started_at=replay.finished_at + timedelta(minutes=2),
        finished_at=replay.finished_at + timedelta(minutes=12))
    rows = CycleMatchService().process(db, battle_id=battle.id, replay=later)
    assert next(row for row in rows if row.user_id == users[2].id).reason == 'membership_changed'
    assert {row.id: row.points for row in db.query(CycleMatchContribution).filter(
        CycleMatchContribution.id.in_(scores))} == scores


def test_ordinary_membership_exclusion_does_not_block_other_players_rating_enrichment(db):
    users, home, _, cycle, battle, replay = match_world(db)
    end_and_return(db, users[2].id, home.id, anchor=CampaignCycleStore.timeline(cycle).battle_at,
        ended=replay.started_at)
    missing = replace(replay, players=tuple(replace(p, historical=False) for p in replay.players))
    first = CycleMatchService().process(db, battle_id=battle.id, replay=missing)
    assert {row.reason for row in first} == {'membership_changed', 'missing_historical_elo'}
    rows = CycleMatchService().process(db, battle_id=battle.id, replay=replay)
    assert {row.reason for row in rows} == {'membership_changed', 'counted'}
    assert db.query(CycleMatchContribution).count() == 2


@pytest.mark.parametrize('returned_role', ['help', 'ambush'])
def test_rejoin_cannot_restore_either_interception_role(db, world, returned_role):
    from tests.test_cycle_interception_service import setup, process
    replay = setup(db, world)
    uid, clan = (world[0][1].id, world[1][0].id) if returned_role == 'help' else (world[0][6].id, world[1][2].id)
    end_and_return(db, uid, clan, anchor=T, ended=T + timedelta(minutes=30), returned=T + timedelta(hours=1))
    rows = process(db, world, replay)
    assert next(row for row in rows if row.user_id == uid).reason == 'membership_changed'
    opponent = next(row for row in rows if row.user_id != uid)
    assert opponent.points == (-50 if returned_role == 'help' else 100)


def test_rejoined_allied_helper_does_not_resume_territorial_points_after_arrival(db, world):
    from app.models.cycle_battle import CycleTerritoryBattle
    from app.services.cycle_reinforcement_store import CycleReinforcementStore
    users, clans, land, cycle = world
    initialize(db, world)
    request(db, world)
    send(db, world)
    CycleReinforcementStore()._resolve_interception(db, cycle_id=cycle.id, dispatch_id='d',
        help_score=100, ambush_scores={clans[2].id: 0}, now=T + timedelta(hours=14, minutes=5))
    end_and_return(db, users[1].id, clans[0].id, anchor=T,
        ended=T + timedelta(hours=20), returned=T + timedelta(hours=21))
    battle = db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle.id, territory_id=land.id).one()
    replay = ReplayFacts('rejoined-help', 'bfmeladder', 'ennorath', True,
        T + timedelta(hours=24), T + timedelta(hours=24, minutes=10),
        (ReplayPlayer(str(UUID(int=2)), 1, 1000, True, 'ennorath'),
         ReplayPlayer(str(UUID(int=6)), 2, 1000, True, 'ennorath')), 1)
    rows = CycleMatchService().process(db, battle_id=battle.id, replay=replay)
    helper = next(row for row in rows if row.user_id == users[1].id)
    assert helper.clan_id == clans[1].id and helper.reason == 'membership_changed' and not helper.counted
    assert next(row for row in rows if row.user_id == users[5].id).points == -50


def test_rejoined_player_can_participate_again_from_a_later_cycle(db):
    from app.services.clan_membership_service import ClanMembershipService
    users, home, _, cycle, _, replay = match_world(db)
    anchor = CampaignCycleStore.timeline(cycle).battle_at
    returned = anchor + timedelta(minutes=3)
    end_and_return(db, users[2].id, home.id, anchor=anchor,
        ended=anchor + timedelta(minutes=2), returned=returned)
    assert not ClanMembershipService.continuous_member_since(db, user_id=users[2].id,
        clan_id=home.id, since=anchor, occurred_at=replay.started_at)
    next_reveal = anchor + timedelta(days=4)
    assert ClanMembershipService.continuous_member_since(db, user_id=users[2].id,
        clan_id=home.id, since=next_reveal, occurred_at=next_reveal + timedelta(minutes=1))


def test_overlapping_membership_history_cannot_confirm_eligibility(db):
    from app.services.clan_membership_service import ClanMembershipService
    users, home, _, cycle, _, replay = match_world(db)
    anchor = CampaignCycleStore.timeline(cycle).battle_at
    db.add_all([
        ClanMembershipPeriod(user_id=users[2].id, clan_id=home.id,
            started_at=anchor - timedelta(days=1), ended_at=replay.finished_at),
        ClanMembershipPeriod(user_id=users[2].id, clan_id=home.id,
            started_at=anchor + timedelta(minutes=1), ended_at=replay.started_at),
    ])
    db.flush()
    assert not ClanMembershipService.continuous_member_since(db, user_id=users[2].id,
        clan_id=home.id, since=anchor, occurred_at=replay.started_at)


def test_legacy_fallback_requires_membership_before_reveal_and_never_overrides_history(db):
    from app.services.clan_membership_service import ClanMembershipService
    users, home, _, cycle, _, replay = match_world(db)
    anchor = CampaignCycleStore.timeline(cycle).battle_at
    member = db.query(ClanMember).filter_by(user_id=users[2].id).one()
    member.joined_at = anchor + timedelta(minutes=1)
    db.flush()
    check = lambda: ClanMembershipService.continuous_member_since(db, user_id=users[2].id,
        clan_id=home.id, since=anchor, occurred_at=replay.started_at)
    assert not check()
    member.joined_at = anchor
    db.flush()
    assert check()
    db.add(ClanMembershipPeriod(user_id=users[2].id, clan_id=home.id,
        started_at=anchor - timedelta(days=1), ended_at=anchor))
    db.flush()
    assert not check()


def test_enrichment_does_not_accept_changed_teams_in_an_excluded_contribution(db):
    users, home, _, cycle, battle, replay = match_world(db)
    end_and_return(db, users[2].id, home.id, anchor=CampaignCycleStore.timeline(cycle).battle_at,
        ended=replay.started_at)
    missing = replace(replay, players=tuple(replace(p, historical=False) for p in replay.players))
    CycleMatchService().process(db, battle_id=battle.id, replay=missing)
    changed = replace(replay, players=tuple(replace(p, team=3 - p.team) for p in replay.players))
    with pytest.raises(ValueError, match='review'):
        CycleMatchService().process(db, battle_id=battle.id, replay=changed)
    assert {row.reason for row in db.query(CycleMatchContribution)} == {'membership_changed', 'missing_historical_elo'}


@pytest.mark.parametrize('case', ['deleted_sender', 'ordinary_exit', 'fake_deletion', 'joined_elsewhere', 'deleted_before_dispatch'])
def test_already_dispatched_help_survives_only_actual_sender_deletion(db, world, case):
    from app.models.cycle_battle import CycleTerritoryBattle
    from app.services.cycle_reinforcement_store import CycleReinforcementStore
    users, clans, land, cycle = world
    initialize(db, world)
    request(db, world)
    send(db, world)
    CycleReinforcementStore()._resolve_interception(db, cycle_id=cycle.id, dispatch_id='d',
        help_score=100, ambush_scores={clans[2].id: 0}, now=T + timedelta(hours=14, minutes=5))
    ended = T - timedelta(seconds=1) if case == 'deleted_before_dispatch' else T + timedelta(hours=20)
    end_and_return(db, users[1].id, clans[0].id, anchor=T, ended=ended)
    period = db.query(ClanMembershipPeriod).filter_by(user_id=users[1].id).one()
    period.ended_reason = 'left' if case == 'ordinary_exit' else 'clan_deleted'
    clans[0].is_deleted = case != 'fake_deletion'
    if case == 'joined_elsewhere':
        db.add(ClanMembershipPeriod(user_id=users[1].id, clan_id=clans[2].id,
            started_at=T + timedelta(hours=21)))
    db.flush()
    battle = db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle.id, territory_id=land.id).one()
    replay = ReplayFacts('deleted-sender', 'bfmeladder', 'ennorath', True,
        T + timedelta(hours=24), T + timedelta(hours=24, minutes=10),
        (ReplayPlayer(str(UUID(int=2)), 1, 1000, True, 'ennorath'),
         ReplayPlayer(str(UUID(int=6)), 2, 1000, True, 'ennorath')), 1)
    rows = CycleMatchService().process(db, battle_id=battle.id, replay=replay)
    helper = next(row for row in rows if row.user_id == users[1].id)
    assert helper.clan_id == clans[1].id
    assert helper.counted is (case == 'deleted_sender')
    assert helper.reason == ('counted' if case == 'deleted_sender' else 'membership_changed')


def test_deleted_sender_help_still_has_to_fight_the_interception(db, world):
    from tests.test_cycle_interception_service import setup, process
    replay = setup(db, world)
    users, clans, _, _ = world
    end_and_return(db, users[1].id, clans[0].id, anchor=T, ended=T + timedelta(hours=1))
    db.query(ClanMembershipPeriod).filter_by(user_id=users[1].id).one().ended_reason = 'clan_deleted'
    clans[0].is_deleted = True
    db.flush()
    rows = process(db, world, replay)
    helper = next(row for row in rows if row.user_id == users[1].id)
    assert helper.counted and helper.points > 0


def test_real_clan_deletion_preserves_dispatched_legacy_membership(db, world, monkeypatch):
    from app.services.clan_service import ClanService
    from app.services.clan_membership_service import ClanMembershipService
    from app.services.cycle_reinforcement_store import decode_state
    users, clans, _, cycle = world
    row = initialize(db, world)
    request(db, world)
    send(db, world)
    dispatch = decode_state(row.payload['state']).dispatches[0]
    monkeypatch.setattr('app.services.clan_service.utc_now', lambda: T + timedelta(hours=1))
    assert ClanService().delete_clan(db, clans[0].id)
    assert ClanMembershipService.dispatched_member_since(db, user_id=users[1].id,
        clan_id=clans[0].id, since=T, occurred_at=T + timedelta(hours=25), dispatch=dispatch)


def test_later_join_does_not_reject_previously_played_dispatched_match(db, world):
    from app.services.clan_membership_service import ClanMembershipService
    from app.services.cycle_reinforcement_store import decode_state
    users, clans, _, _ = world
    row = initialize(db, world)
    request(db, world)
    send(db, world)
    dispatch = decode_state(row.payload['state']).dispatches[0]
    end_and_return(db, users[1].id, clans[0].id, anchor=T, ended=T + timedelta(hours=1))
    db.query(ClanMembershipPeriod).filter_by(user_id=users[1].id).one().ended_reason = 'clan_deleted'
    clans[0].is_deleted = True
    later = T + timedelta(hours=30)
    db.add(ClanMember(user_id=users[1].id, clan_id=clans[2].id, joined_at=later))
    db.add(ClanMembershipPeriod(user_id=users[1].id, clan_id=clans[2].id, started_at=later))
    db.flush()
    assert ClanMembershipService.dispatched_member_since(db, user_id=users[1].id,
        clan_id=clans[0].id, since=T, occurred_at=T + timedelta(hours=25), dispatch=dispatch)
