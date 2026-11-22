from dataclasses import replace
from datetime import timedelta

import pytest

from app.models.cycle_interception import CycleInterception
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_arena_ingestion_service import CycleArenaIngestionService
from app.services.cycle_match_service import CycleMatchService
from tests.test_cycle_arena_ingestion import saved
from tests.test_cycle_interception_service import setup
from tests.test_cycle_match_service import match_world
from tests.test_cycle_reinforcement_store import world, T


def scan(start, end, replay_ids=frozenset()):
    from app.services.arena_replay_scan import ArenaReplayScan
    return ArenaReplayScan(start, end, 'bfmeladder:test-complete-scan', replay_ids=replay_ids)


def verify(db, evidence, now):
    return CycleArenaIngestionService().verify_pending(db, scan=evidence, now=now)


def test_full_saved_scan_verifies_empty_cycle_without_invented_matches(db):
    _, _, _, cycle, _, _ = match_world(db)
    timeline = CampaignCycleStore.timeline(cycle)
    evidence = scan(timeline.battle_at, timeline.replay_deadline)
    result = verify(db, evidence, timeline.replay_deadline)
    assert result == {'cycles_verified': 1, 'interceptions_verified': 0, 'interceptions_settled': 0}
    assert cycle.import_verified_at is not None
    revision = cycle.revision
    verify(db, evidence, timeline.replay_deadline)
    assert cycle.revision == revision


@pytest.mark.parametrize('boundary', ['late_start', 'before_grace', 'future_end', 'no_scan'])
def test_time_or_heartbeat_alone_cannot_verify_source(db, boundary):
    _, _, _, cycle, _, _ = match_world(db)
    timeline = CampaignCycleStore.timeline(cycle)
    evidence = scan(timeline.battle_at, timeline.replay_deadline)
    now = timeline.replay_deadline
    if boundary == 'late_start':
        evidence = replace(evidence, covered_start=timeline.battle_at + timedelta(milliseconds=1))
    elif boundary == 'before_grace':
        evidence = replace(evidence, covered_end=timeline.replay_deadline - timedelta(milliseconds=1))
    elif boundary == 'future_end':
        now -= timedelta(milliseconds=1)
    else:
        evidence = None
    result = verify(db, evidence, now)
    assert result['cycles_verified'] == 0
    assert cycle.import_verified_at is None


def test_missing_elo_blocks_completion_even_after_complete_network_scan(db):
    _, _, _, cycle, _, facts = match_world(db)
    saved(db, facts)
    timeline = CampaignCycleStore.timeline(cycle)
    importer = CycleArenaIngestionService()
    importer.ingest_pending(db, now=timeline.replay_deadline)
    result = verify(db, scan(timeline.battle_at, timeline.replay_deadline), timeline.replay_deadline)
    assert result['cycles_verified'] == 0
    assert cycle.import_verified_at is None


def test_verified_personal_results_allow_full_scan_completion(db):
    _, _, _, cycle, battle, facts = match_world(db)
    CycleMatchService().process(db, battle_id=battle.id, replay=facts)
    timeline = CampaignCycleStore.timeline(cycle)
    verify(db, scan(timeline.battle_at, timeline.replay_deadline), timeline.replay_deadline)
    assert cycle.import_verified_at is not None


def test_source_error_prevents_verifying_empty_interception(db, world):
    setup(db, world)
    cycle = world[3]
    cycle.dependencies = {**cycle.dependencies, 'source-replay:999': False}
    db.flush()
    result = verify(db, scan(T, T + timedelta(hours=14, minutes=5)), T + timedelta(hours=14, minutes=5))
    assert result['interceptions_settled'] == 0
    assert db.query(CycleInterception).count() == 0
    assert cycle.dependencies['interception:d'] is False


def test_complete_scan_resolves_no_game_interception_after_its_own_grace(db, world):
    setup(db, world)
    cycle = world[3]
    end = T + timedelta(hours=14, minutes=5)
    evidence = scan(T, end)
    result = verify(db, evidence, end)
    assert result['interceptions_verified'] == result['interceptions_settled'] == 1
    assert cycle.dependencies['interception:d'] is True
    assert cycle.import_verified_at is None
    assert verify(db, evidence, end)['interceptions_settled'] == 0


def test_interception_scan_taken_before_grace_is_not_reused_after_grace(db, world):
    setup(db, world)
    end = T + timedelta(hours=14, minutes=5)
    result = verify(db, scan(T, end - timedelta(milliseconds=1)), end + timedelta(minutes=1))
    assert result['interceptions_verified'] == 0
    assert world[3].dependencies['interception:d'] is False


def test_interception_with_missing_elo_is_not_settled_as_zero_games(db, world):
    facts = setup(db, world)
    saved(db, facts)
    end = T + timedelta(hours=14, minutes=5)
    CycleArenaIngestionService().ingest_pending(db, now=end)
    result = verify(db, scan(T, end), end)
    assert result['interceptions_settled'] == 0
    assert world[3].dependencies['interception:d'] is False


def test_completed_or_legacy_cycle_never_gets_new_scan_attestation(db):
    from app.models.campaign import CampaignSeason
    _, _, _, cycle, _, _ = match_world(db)
    timeline = CampaignCycleStore.timeline(cycle)
    season = db.get(CampaignSeason, cycle.season_id)
    season.rules_snapshot = {**season.rules_snapshot, 'mechanics_version': 'legacy'}
    db.flush()
    verify(db, scan(timeline.battle_at, timeline.replay_deadline), timeline.replay_deadline)
    assert cycle.import_verified_at is None


def test_verifier_processes_saved_games_before_certifying_zero_score(db):
    _, _, _, cycle, _, facts = match_world(db)
    saved(db, facts)
    timeline = CampaignCycleStore.timeline(cycle)
    result = verify(db, scan(timeline.battle_at, timeline.replay_deadline), timeline.replay_deadline)
    assert result['cycles_verified'] == 0
    assert cycle.import_verified_at is None


def test_worker_passes_committed_scan_to_verification_before_settlement(db, monkeypatch):
    import asyncio
    from contextlib import nullcontext
    import app.services.scheduler_service as scheduler
    _, _, _, cycle, _, _ = match_world(db)
    timeline = CampaignCycleStore.timeline(cycle)
    evidence = scan(timeline.battle_at, timeline.replay_deadline)
    calls = []

    class Runtime:
        def tick(self, db, *, now, allow_settlement=True):
            calls.append(allow_settlement)
            if allow_settlement:
                assert cycle.import_verified_at is not None
            return True

    class Ladder:
        last_completed_scan = None

        async def fetch_and_save_matches(self, db, limit):
            db.commit()
            self.last_completed_scan = evidence
            return 0

    class Backfill:
        async def process_pending(self, db):
            return 0

    monkeypatch.setattr(scheduler, 'SessionLocal', lambda: nullcontext(db))
    monkeypatch.setattr(scheduler, 'CycleRuntimeService', Runtime)
    monkeypatch.setattr(scheduler, 'BFMELadderService', Ladder)
    monkeypatch.setattr(scheduler, 'ArenaMatchBackfillService', Backfill)
    monkeypatch.setattr(scheduler, '_utcnow', lambda: timeline.replay_deadline)
    asyncio.run(scheduler.CampaignWorker().run_cycle())
    assert calls == [False, True]


def test_error_after_interception_verification_rolls_back_all_proofs(db, world, monkeypatch):
    setup(db, world)
    cycle = world[3]
    deadline = CampaignCycleStore.timeline(cycle).replay_deadline
    db.commit()
    original = CampaignCycleStore.mark_import_complete

    def fail(self, db, **kwargs):
        original(self, db, **kwargs)
        raise RuntimeError('Ошибка после подтверждения загрузки')

    monkeypatch.setattr(CampaignCycleStore, 'mark_import_complete', fail)
    with pytest.raises(RuntimeError):
        verify(db, scan(T, deadline), deadline)
    assert db.query(CycleInterception).count() == 0
    assert cycle.dependencies['interception:d'] is False
    assert cycle.import_verified_at is None


def test_source_scan_replay_is_not_lost_because_old_cached_date_is_outside_cycle(db):
    from app.models.cycle_battle import CycleMatchContribution
    _, _, _, cycle, _, facts = match_world(db)
    match = saved(db, facts)
    match.match_date -= timedelta(days=10)
    db.flush()
    timeline = CampaignCycleStore.timeline(cycle)
    evidence = scan(timeline.battle_at, timeline.replay_deadline, frozenset({facts.replay_id}))
    verify(db, evidence, timeline.replay_deadline)
    assert cycle.import_verified_at is None
    assert {r.reason for r in db.query(CycleMatchContribution)} == {'missing_historical_elo'}


def test_missing_duration_and_old_cached_date_do_not_hide_interception_game(db, world):
    from app.models.cycle_interception import CycleInterceptionContribution
    facts = setup(db, world)
    match = saved(db, facts, raw_changes={'duration': None})
    match.match_date -= timedelta(days=10)
    db.flush()
    end = T + timedelta(hours=14, minutes=5)
    result = verify(db, scan(T, end, frozenset({facts.replay_id})), end)
    assert result['interceptions_settled'] == 0
    assert {r.reason for r in db.query(CycleInterceptionContribution)} == {'missing_match_times'}


def test_unknown_source_start_cannot_resolve_interception_as_empty(db, world):
    facts = setup(db, world)
    match = saved(db, facts, raw_changes={'date': None})
    match.match_date -= timedelta(days=10)
    db.flush()
    end = T + timedelta(hours=14, minutes=5)
    result = verify(db, scan(T, end, frozenset({facts.replay_id})), end)
    assert result['interceptions_settled'] == 0
    assert world[3].dependencies[f'source-replay:{match.id}'] is False


def test_corrected_source_date_outside_cycle_clears_pending_dependency_and_receipts(db):
    from copy import deepcopy
    from app.models.cycle_battle import CycleMatchContribution
    _, _, _, cycle, _, facts = match_world(db)
    match = saved(db, facts, raw_changes={'date': None})
    match.match_date -= timedelta(days=10)
    db.flush()
    timeline = CampaignCycleStore.timeline(cycle)
    evidence = scan(timeline.battle_at - timedelta(days=1), timeline.replay_deadline, frozenset({facts.replay_id}))
    verify(db, evidence, timeline.replay_deadline)
    assert cycle.dependencies[f'source-replay:{match.id}'] is False
    payload = deepcopy(match.source_payload)
    payload['PublicApiPayload']['date'] = int((timeline.battle_at - timedelta(hours=1)).timestamp() * 1000)
    match.source_payload = payload
    db.flush()
    verify(db, evidence, timeline.replay_deadline)
    assert cycle.dependencies[f'source-replay:{match.id}'] is True
    assert {r.reason for r in db.query(CycleMatchContribution)} == {'outside_battle_window'}
    assert cycle.import_verified_at is not None


def test_corrected_interception_date_outside_window_resolves_old_pending_receipts(db, world):
    from copy import deepcopy
    from app.models.cycle_interception import CycleInterceptionContribution
    facts = setup(db, world)
    match = saved(db, facts, raw_changes={'duration': None})
    match.match_date -= timedelta(days=10)
    db.flush()
    end = T + timedelta(hours=14, minutes=5)
    evidence = scan(T - timedelta(days=1), end, frozenset({facts.replay_id}))
    verify(db, evidence, end)
    payload = deepcopy(match.source_payload)
    payload['PublicApiPayload'].update(date=int((T - timedelta(hours=1)).timestamp() * 1000), duration='00:10:00')
    match.source_payload = payload
    db.flush()
    result = verify(db, evidence, end)
    assert {r.reason for r in db.query(CycleInterceptionContribution)} == {'outside_battle_window'}
    assert result['interceptions_settled'] == 1
