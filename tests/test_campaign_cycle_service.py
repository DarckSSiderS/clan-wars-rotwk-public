from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from app.services.campaign_cycle_service import CampaignCycle, CyclePhase


START = datetime(2026, 10, 15, tzinfo=timezone.utc)


def test_first_cycle_starts_after_registration_and_preserves_rule_version():
    cycle = CampaignCycle.first(season_id=4, rule_version=7, starts_at=START)
    assert cycle.number == 1
    assert cycle.season_id == 4
    assert cycle.rule_version == 7
    assert cycle.preparation_at == START + timedelta(hours=72)
    assert cycle.battle_at == START + timedelta(hours=96)
    assert cycle.battle_ends_at == START + timedelta(hours=144)
    assert cycle.replay_deadline == cycle.battle_ends_at + timedelta(minutes=5)
    with pytest.raises(FrozenInstanceError):
        cycle.rule_version = 8


@pytest.mark.parametrize('offset,phase', [
    (timedelta(), CyclePhase.REGISTRATION),
    (timedelta(hours=72), CyclePhase.PREPARATION),
    (timedelta(hours=96), CyclePhase.BATTLE),
    (timedelta(hours=144), CyclePhase.REPLAY_LOADING),
    (timedelta(hours=144, minutes=5), CyclePhase.SETTLEMENT),
    (timedelta(days=30), CyclePhase.SETTLEMENT),
])
def test_exact_phase_boundaries_and_outage_do_not_skip_settlement(offset, phase):
    cycle = CampaignCycle.first(season_id=4, rule_version=7, starts_at=START)
    assert cycle.phase_at(START + offset) == phase


def test_full_rest_and_preparation_follow_actual_successful_settlement():
    cycle = CampaignCycle.first(season_id=4, rule_version=7, starts_at=START)
    recovered_at = cycle.replay_deadline + timedelta(days=3)
    settled = cycle.settle(recovered_at)
    assert cycle.settled_at is None
    assert settled.phase_at(recovered_at) == CyclePhase.REST
    assert settled.phase_at(recovered_at + timedelta(hours=12)) == CyclePhase.COMPLETE
    following = settled.next_cycle(rule_version=8)
    assert following.number == 2
    assert following.season_id == cycle.season_id
    assert following.rule_version == 8
    assert following.preparation_at == recovered_at + timedelta(hours=12)
    assert following.battle_at == recovered_at + timedelta(hours=36)
    assert following.phase_at(following.preparation_at) == CyclePhase.PREPARATION


def test_repeated_settlement_does_not_shift_the_calendar():
    cycle = CampaignCycle.first(season_id=1, rule_version=1, starts_at=START)
    settled = cycle.settle(cycle.replay_deadline)
    assert settled.settle(cycle.replay_deadline + timedelta(days=1)) == settled


def test_cannot_settle_early_or_start_next_cycle_before_settlement():
    cycle = CampaignCycle.first(season_id=1, rule_version=1, starts_at=START)
    with pytest.raises(ValueError):
        cycle.settle(cycle.battle_ends_at)
    with pytest.raises(ValueError):
        cycle.next_cycle(rule_version=1)


def test_end_request_waits_for_calculation_and_prevents_next_cycle():
    cycle = CampaignCycle.first(season_id=1, rule_version=1, starts_at=START)
    ending = cycle.request_season_end()
    assert ending.request_season_end() == ending
    assert ending.phase_at(ending.replay_deadline) == CyclePhase.SETTLEMENT
    settled = ending.settle(ending.replay_deadline)
    assert settled.phase_at(settled.settled_at) == CyclePhase.SEASON_ENDED
    with pytest.raises(ValueError):
        settled.next_cycle(rule_version=1)


def test_game_window_includes_finish_at_deadline_but_not_start_at_deadline():
    cycle = CampaignCycle.first(season_id=1, rule_version=1, starts_at=START)
    end = cycle.battle_ends_at
    assert cycle.accepts_match(end - timedelta(minutes=1), end)
    assert not cycle.accepts_match(end, end + timedelta(minutes=1))
    assert not cycle.accepts_match(end - timedelta(seconds=59), end)
    assert not cycle.accepts_match(cycle.battle_at - timedelta(seconds=1), cycle.battle_at + timedelta(minutes=1))
    assert not cycle.accepts_match(end - timedelta(minutes=1), end + timedelta(seconds=1))


def test_reserve_dispatch_and_arrival_boundaries():
    cycle = CampaignCycle.first(season_id=1, rule_version=1, starts_at=START)
    assert cycle.reinforcement_arrival(cycle.battle_at) == cycle.battle_at + timedelta(hours=24)
    latest = cycle.battle_at + timedelta(hours=24) - timedelta(microseconds=1)
    assert cycle.reinforcement_arrival(latest) == latest + timedelta(hours=24)
    for invalid in (cycle.preparation_at, cycle.battle_at + timedelta(hours=24)):
        with pytest.raises(ValueError):
            cycle.reinforcement_arrival(invalid)


def test_requires_aware_time_and_normalizes_to_utc():
    with pytest.raises(ValueError):
        CampaignCycle.first(season_id=1, rule_version=1, starts_at=START.replace(tzinfo=None))
    local = START.astimezone(timezone(timedelta(hours=3)))
    cycle = CampaignCycle.first(season_id=1, rule_version=1, starts_at=local)
    assert cycle.starts_at == START
    assert cycle.starts_at.tzinfo == timezone.utc
    with pytest.raises(ValueError):
        cycle.phase_at(START.replace(tzinfo=None))


@pytest.mark.parametrize('season_id,version', [(0, 1), (1, 0), (-1, 1)])
def test_requires_valid_persistent_identifiers(season_id, version):
    with pytest.raises(ValueError):
        CampaignCycle.first(season_id=season_id, rule_version=version, starts_at=START)


def test_repeated_next_cycle_planning_is_deterministic():
    cycle = CampaignCycle.first(season_id=1, rule_version=2, starts_at=START)
    settled = cycle.settle(cycle.replay_deadline)
    assert settled.next_cycle(rule_version=3) == settled.next_cycle(rule_version=3)
    assert settled.rule_version == 2
    assert settled.number == 1


def test_historical_phase_is_not_changed_by_later_settlement():
    cycle = CampaignCycle.first(season_id=1, rule_version=2, starts_at=START)
    settled = cycle.settle(cycle.replay_deadline + timedelta(hours=8))
    assert settled.phase_at(cycle.replay_deadline) == CyclePhase.SETTLEMENT
    assert settled.phase_at(cycle.battle_at) == CyclePhase.BATTLE


def test_invalid_persisted_timeline_is_rejected():
    with pytest.raises(ValueError):
        CampaignCycle(season_id=1, rule_version=1, number=1,
                      starts_at=START, preparation_at=START - timedelta(seconds=1))
    cycle = CampaignCycle.first(season_id=1, rule_version=1, starts_at=START)
    with pytest.raises(ValueError):
        CampaignCycle(season_id=1, rule_version=1, number=1,
                      starts_at=START, preparation_at=cycle.preparation_at,
                      settled_at=cycle.battle_ends_at)
    with pytest.raises(ValueError):
        cycle.phase_at(START - timedelta(seconds=1))
