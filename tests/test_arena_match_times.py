from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.services.cycle_match_service import CycleMatchService, ReplayFacts, ReplayPlayer
from tests.test_cycle_reinforcement_store import world


def facts():
    return ReplayFacts('arena-time', 'bfmeladder', 'ennorath', True, None, None,
        (ReplayPlayer('00000000-0000-0000-0000-000000000001', 1, None, False, None),
         ReplayPlayer('00000000-0000-0000-0000-000000000002', 2, None, False, None)), 1)


@pytest.mark.parametrize('date', [1792324856619, '1792324856619'])
def test_arena_date_is_start_and_duration_is_added_without_rounding(date):
    original = facts()
    result = original.with_arena_times(date_ms=date, duration='01:02:03')
    expected = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=int(date))
    assert result.started_at == expected
    assert result.finished_at == expected + timedelta(hours=1, minutes=2, seconds=3)
    assert original.started_at is None and original.finished_at is None
    assert result.players == original.players
    assert all(not player.historical and player.elo is None for player in result.players)


@pytest.mark.parametrize(('date', 'duration'), [
    (None, '00:10:00'), (True, '00:10:00'), (-1, '00:10:00'),
    (1792324856619.5, '00:10:00'), ('1792324856619.5', '00:10:00'),
    ('2026-10-18', '00:10:00'), (10**30, '00:10:00'),
    (1792324856619, None), (1792324856619, ''),
    (1792324856619, '-1:00:00'), (1792324856619, '00:60:00'),
    (1792324856619, '00:00:60'), (1792324856619, 'ten minutes'),
])
def test_malformed_source_times_remain_missing_instead_of_guessing(date, duration):
    result = facts().with_arena_times(date_ms=date, duration=duration)
    assert result.started_at is None and result.finished_at is None


def test_epoch_and_zero_duration_are_not_confused_with_missing_values():
    result = facts().with_arena_times(date_ms=0, duration='00:00:00')
    assert result.started_at == result.finished_at == datetime(1970, 1, 1, tzinfo=timezone.utc)


def test_existing_minutes_seconds_duration_format_is_supported():
    result = facts().with_arena_times(date_ms=0, duration='62:03')
    assert result.finished_at - result.started_at == timedelta(minutes=62, seconds=3)


def test_arena_time_conversion_cannot_be_applied_to_another_source():
    with pytest.raises(ValueError, match='Arena'):
        replace(facts(), source='another').with_arena_times(date_ms=0, duration='00:10:00')


@pytest.mark.parametrize(('duration', 'reason'), [
    ('00:00:59', 'too_short'), ('00:01:00', 'counted'),
])
def test_arena_times_feed_actual_cycle_minute_boundary(db, duration, reason):
    from tests.test_cycle_match_service import match_world
    _, _, _, _, battle, replay = match_world(db)
    source = replay.with_arena_times(date_ms=int(replay.started_at.timestamp() * 1000), duration=duration)
    rows = CycleMatchService().process(db, battle_id=battle.id, replay=source)
    assert {row.reason for row in rows} == {reason}


def test_confirmed_times_do_not_certify_current_elo_or_import_completion(db):
    from tests.test_cycle_match_service import match_world
    _, _, _, cycle, battle, replay = match_world(db)
    replay = replace(replay, players=tuple(replace(player, historical=False) for player in replay.players))
    source = replay.with_arena_times(date_ms=int(replay.started_at.timestamp() * 1000), duration='00:10:00')
    rows = CycleMatchService().process(db, battle_id=battle.id, replay=source)
    assert {row.reason for row in rows} == {'missing_historical_elo'}
    assert all(not row.counted for row in rows)
    assert cycle.import_verified_at is None


@pytest.mark.parametrize(('duration', 'reason'), [
    ('00:01:00', 'counted'), ('00:01:01', 'outside_battle_window'),
])
def test_arena_game_must_finish_inside_territory_battle(db, duration, reason):
    from tests.test_cycle_match_service import match_world
    from app.services.campaign_cycle_store import CampaignCycleStore
    _, _, _, cycle, battle, replay = match_world(db)
    start = CampaignCycleStore.timeline(cycle).battle_ends_at - timedelta(minutes=1)
    source = replay.with_arena_times(date_ms=int(start.timestamp() * 1000), duration=duration)
    rows = CycleMatchService().process(db, battle_id=battle.id, replay=source)
    assert {row.reason for row in rows} == {reason}


@pytest.mark.parametrize(('duration', 'reason'), [
    ('00:01:00', 'counted'), ('00:01:01', 'outside_battle_window'),
])
def test_arena_game_must_finish_inside_interception(db, world, duration, reason):
    from tests.test_cycle_interception_service import setup, process, T
    replay = setup(db, world)
    start = T + timedelta(hours=14) - timedelta(minutes=1)
    source = replay.with_arena_times(date_ms=int(start.timestamp() * 1000), duration=duration)
    rows = process(db, world, source)
    assert {row.reason for row in rows} == {reason}
