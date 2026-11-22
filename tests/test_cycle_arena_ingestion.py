from copy import deepcopy
from datetime import timedelta
from uuid import UUID

import pytest

from app.models.match import Match, MatchParticipant
from app.models.cycle_battle import CycleMatchContribution
from app.models.cycle_interception import CycleInterceptionContribution
from app.services.ladder_service import BFMELadderService
from tests.test_cycle_match_service import match_world
from tests.test_cycle_reinforcement_store import world


def service():
    from app.services.cycle_arena_ingestion_service import CycleArenaIngestionService
    return CycleArenaIngestionService()


def saved(db, replay, *, raw_changes=None):
    raw = dict(replayId=replay.replay_id, gameName='RotWK', patchName='Ennorath',
        gamemode=f'{len(replay.players) // 2} versus {len(replay.players) // 2}',
        date=int(replay.started_at.timestamp() * 1000), duration='00:10:00',
        players=[dict(uuid=player.uuid, team=player.team, isWinner=player.team == replay.winning_team,
            oldRank=10, newRank=11) for player in replay.players])
    raw.update(raw_changes or {})
    _, payload = BFMELadderService._normalize_public_replay(raw)
    row = Match(match_id=replay.replay_id, winner_player='Old visible name', winner_faction='elves',
        loser_player='Another name', loser_faction='men', game_name='RotWK', is_live=False,
        match_date=replay.started_at, source_payload=payload,
        winner_elo=9999, loser_elo=9999, rating_source='bfmeladder_current')
    db.add(row)
    db.flush()
    return row


def test_real_public_payload_adapts_only_uuid_and_confirmed_times(db):
    _, _, _, _, _, replay = match_world(db)
    match = saved(db, replay)
    result = service().adapt(match)
    assert result.started_at == replay.started_at
    assert result.finished_at == replay.started_at + timedelta(minutes=10)
    assert [p.uuid for p in result.players] == [p.uuid for p in replay.players]
    assert result.ranked and result.winning_team == replay.winning_team
    assert all(p.elo is None and not p.historical for p in result.players)


def test_ingestion_routes_renamed_players_by_source_uuid_once_without_points(db):
    users, _, _, cycle, battle, replay = match_world(db)
    match = saved(db, replay)
    users[2].username = 'Name changed again'
    db.add(MatchParticipant(match_id=match.id, nickname=users[2].username,
        player_uuid=str(UUID(int=999)), team=1, is_winner=True, elo=9999))
    db.flush()
    importer = service()
    first = importer.ingest_cycle(db, cycle_id=cycle.id, now=replay.finished_at)
    again = importer.ingest_cycle(db, cycle_id=cycle.id, now=replay.finished_at)
    rows = db.query(CycleMatchContribution).filter_by(battle_id=battle.id).all()
    assert len(rows) == 2
    assert {row.user_id for row in rows} == {users[2].id, users[3].id}
    assert {row.reason for row in rows} == {'missing_historical_elo'}
    assert all(not row.counted and row.points == 0 for row in rows)
    assert first['territory_receipts'] == again['territory_receipts'] == 2
    assert cycle.import_verified_at is None


@pytest.mark.parametrize('broken', ['uuid', 'duplicate', 'team_size', 'html_only', 'replay_id'])
def test_ambiguous_source_is_not_repaired_from_names_or_stored_participants(db, broken):
    _, _, _, cycle, _, replay = match_world(db)
    match = saved(db, replay)
    payload = deepcopy(match.source_payload)
    raw = payload['PublicApiPayload']
    if broken == 'uuid':
        raw['players'][0]['uuid'] = None
    elif broken == 'duplicate':
        raw['players'][1]['uuid'] = raw['players'][0]['uuid']
    elif broken == 'team_size':
        raw['gamemode'] = '2 versus 2'
    elif broken == 'html_only':
        payload.pop('PublicApiPayload')
    else:
        raw['replayId'] = 'another-replay'
    match.source_payload = payload
    db.flush()
    report = service().ingest_cycle(db, cycle_id=cycle.id, now=replay.finished_at)
    assert report['source_errors'] == 1
    assert db.query(CycleMatchContribution).count() == 0
    assert cycle.import_verified_at is None


def test_pending_pipeline_cannot_downgrade_existing_verified_scores(db):
    from app.services.cycle_match_service import CycleMatchService
    _, _, _, cycle, battle, replay = match_world(db)
    saved(db, replay)
    CycleMatchService().process(db, battle_id=battle.id, replay=replay)
    before = [(row.id, row.points, row.counted, row.calculation) for row in
        db.query(CycleMatchContribution).order_by(CycleMatchContribution.id)]
    service().ingest_cycle(db, cycle_id=cycle.id, now=replay.finished_at)
    after = [(row.id, row.points, row.counted, row.calculation) for row in
        db.query(CycleMatchContribution).order_by(CycleMatchContribution.id)]
    assert before == after


def test_unrelated_and_outside_window_matches_do_not_create_receipts(db):
    from dataclasses import replace
    _, _, _, cycle, _, replay = match_world(db)
    outside = replace(replay, replay_id='before-battle', started_at=replay.started_at - timedelta(days=4))
    saved(db, outside)
    unrelated = replace(replay, replay_id='unrelated', players=tuple(
        replace(p, uuid=str(UUID(int=100 + n))) for n, p in enumerate(replay.players)))
    saved(db, unrelated)
    service().ingest_cycle(db, cycle_id=cycle.id, now=replay.finished_at)
    assert db.query(CycleMatchContribution).count() == 0


@pytest.mark.parametrize('detail', ['invalid', 'other-replay', 'comment', 'not-invalid', 'in-api', 'partial-scan'])
@pytest.mark.asyncio
async def test_old_html_match_requires_explicit_same_replay_invalidation(db, detail):
    from app.services.arena_replay_scan import ArenaReplayScan
    from app.services.campaign_cycle_store import CampaignCycleStore

    _, _, _, cycle, _, replay = match_world(db)
    match = saved(db, replay)
    match.source_payload = dict(ReplayId=match.match_id, Source='bfme_arena_html')
    timeline = CampaignCycleStore.timeline(cycle)
    deadline = timeline.replay_deadline
    end = deadline - timedelta(seconds=1) if detail == 'partial-scan' else deadline
    ids = frozenset({match.match_id}) if detail == 'in-api' else frozenset()
    scan = ArenaReplayScan(timeline.battle_at, end, 'full-scan', ids)
    marker = '<span style="color:var(--loss);">invalid</span>'
    header_marker = '' if detail == 'comment' else marker.replace(
        '>invalid<', '>valid<' if detail == 'not-invalid' else '>invalid<')
    rid = 'some-other-replay' if detail == 'other-replay' else match.match_id
    html = f'''<html><body><main><div class="container page"><div class="page-head"><h1>Map</h1></div>
      <div><span>2026-11-08 19:54 UTC</span><span>00:17:55</span>{header_marker}</div>
      <div><a href="/api/replays/download?replayId={rid}">Download</a></div></div>
      <div class="comments">{marker if detail == 'comment' else ''}</div></main></body></html>'''

    class Response:
        status = 200
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def text(self):
            return html

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    importer = service()
    importer.ingest_cycle(db, cycle_id=cycle.id, now=deadline)
    assert cycle.dependencies[f'source-replay:{match.id}'] is False
    await BFMELadderService()._check_old_html_rejections(Session(), db, scan, deadline)
    report = importer.verify_pending(db, scan=scan, now=deadline)
    assert report['cycles_verified'] == (detail == 'invalid')
    assert cycle.dependencies[f'source-replay:{match.id}'] is (detail == 'invalid')
    assert db.query(CycleMatchContribution).count() == 0


def test_interception_and_territorial_receipts_remain_separate(db, world):
    from tests.test_cycle_interception_service import setup
    replay = setup(db, world)
    saved(db, replay)
    cycle = world[3]
    report = service().ingest_cycle(db, cycle_id=cycle.id, now=replay.finished_at)
    assert report['interception_receipts'] == 2
    rows = db.query(CycleInterceptionContribution).all()
    assert {row.reason for row in rows} == {'missing_historical_elo'}
    assert all(not row.counted and row.points == 0 for row in rows)
    assert cycle.dependencies['interception:d'] is False
    assert cycle.import_verified_at is None


def test_settled_cycle_is_never_reopened_by_automatic_ingestion(db):
    from app.services.campaign_cycle_store import CampaignCycleStore
    _, _, _, cycle, _, replay = match_world(db)
    saved(db, replay)
    cycle.settled_at = CampaignCycleStore.timeline(cycle).replay_deadline
    db.flush()
    report = service().ingest_pending(db, now=cycle.settled_at + timedelta(days=1))
    assert report['cycles'] == 0
    assert db.query(CycleMatchContribution).count() == 0


def test_new_receipt_invalidates_previous_import_attestation(db):
    from app.services.campaign_cycle_store import CampaignCycleStore
    from app.services.cycle_match_service import CycleMatchService
    _, _, _, cycle, battle, replay = match_world(db)
    cycle.import_verified_at = CampaignCycleStore.timeline(cycle).replay_deadline
    db.flush()
    CycleMatchService().process(db, battle_id=battle.id, replay=replay)
    assert cycle.import_verified_at is None


def test_incomplete_source_clears_old_attestation_without_invented_identity(db):
    from app.services.campaign_cycle_store import CampaignCycleStore
    _, _, _, cycle, _, replay = match_world(db)
    match = saved(db, replay)
    match.source_payload = {'Players': []}
    cycle.import_verified_at = CampaignCycleStore.timeline(cycle).replay_deadline
    db.flush()
    report = service().ingest_cycle(db, cycle_id=cycle.id, now=replay.finished_at)
    assert report['source_errors'] == 1
    assert cycle.import_verified_at is None


def test_worker_ingests_saved_network_results_into_pending_cycle_receipts(db, monkeypatch):
    import asyncio
    from contextlib import nullcontext
    import app.services.scheduler_service as scheduler
    users, _, _, cycle, _, replay = match_world(db)
    seen = []

    class Runtime:
        def tick(self, db, *, now, allow_settlement=True):
            seen.append(db.query(CycleMatchContribution).count())
            return True

    class Ladder:
        async def fetch_and_save_matches(self, db, limit):
            saved(db, replay)
            db.commit()
            return 1

    monkeypatch.setattr(scheduler, 'SessionLocal', lambda: nullcontext(db))
    monkeypatch.setattr(scheduler, 'CycleRuntimeService', Runtime)
    monkeypatch.setattr(scheduler, 'BFMELadderService', Ladder)
    monkeypatch.setattr(scheduler, '_utcnow', lambda: replay.finished_at + timedelta(minutes=1))
    assert asyncio.run(scheduler.CampaignWorker().run_cycle()) == 1
    assert seen == [0, 2]
    assert {row.user_id for row in db.query(CycleMatchContribution)} == {users[2].id, users[3].id}
    assert cycle.import_verified_at is None


def test_import_cannot_be_certified_while_personal_source_evidence_is_pending(db):
    from app.services.campaign_cycle_store import CampaignCycleStore
    _, _, _, cycle, _, replay = match_world(db)
    saved(db, replay)
    service().ingest_cycle(db, cycle_id=cycle.id, now=replay.finished_at)
    with pytest.raises(ValueError, match='Pending'):
        CampaignCycleStore().mark_import_complete(db, cycle_id=cycle.id,
            verified_at=CampaignCycleStore.timeline(cycle).replay_deadline)
    assert cycle.import_verified_at is None


@pytest.mark.parametrize('payload', [[], 'not a source response'])
def test_malformed_stored_source_is_reported_without_losing_other_matches(db, payload):
    from dataclasses import replace
    _, _, _, cycle, _, replay = match_world(db)
    bad = saved(db, replay)
    bad.source_payload = payload
    saved(db, replace(replay, replay_id='valid-next-match'))
    db.flush()
    report = service().ingest_cycle(db, cycle_id=cycle.id, now=replay.finished_at)
    assert report['source_errors'] == 1
    assert db.query(CycleMatchContribution).count() == 2


def test_team_mode_keeps_all_four_uuid_participants_without_splitting_or_inventing_elo(db):
    from dataclasses import replace
    from app.services.cycle_match_service import ReplayPlayer
    _, _, _, _, _, replay = match_world(db)
    replay = replace(replay, players=(*replay.players,
        ReplayPlayer(str(UUID(int=500)), 1, 1234, True, 'ennorath'),
        ReplayPlayer(str(UUID(int=501)), 2, 1400, True, 'ennorath')))
    match = saved(db, replay)
    result = service().adapt(match)
    assert len(result.players) == 4
    assert [p.team for p in result.players] == [1, 2, 1, 2]
    assert all(p.elo is None and not p.historical for p in result.players)


def test_incomplete_result_is_pending_not_a_guessed_loss(db):
    _, _, _, cycle, _, replay = match_world(db)
    match = saved(db, replay)
    payload = deepcopy(match.source_payload)
    payload['PublicApiPayload']['players'][0].pop('isWinner')
    match.source_payload = payload
    db.flush()
    report = service().ingest_cycle(db, cycle_id=cycle.id, now=replay.finished_at)
    assert report['pending_receipts'] == 2
    assert {row.reason for row in db.query(CycleMatchContribution)} == {'unknown_result'}


def test_uuid_evidence_survives_html_metadata_refresh_of_same_replay(db):
    _, _, _, _, _, replay = match_world(db)
    match = saved(db, replay)
    expected = deepcopy(match.source_payload['PublicApiPayload'])
    BFMELadderService._apply_api_replay_metadata(match, {
        'ReplayId': replay.replay_id, 'Date': expected['date'],
        'Players': [{'DisplayName': 'Changed name'}], 'IsValid': True})
    result = service().adapt(match)
    assert [p.uuid for p in result.players] == [p.uuid for p in replay.players]
    assert match.source_payload['PublicApiPayload'] == expected


def test_ingestion_rolls_back_all_new_receipts_if_one_target_fails(db, monkeypatch):
    from dataclasses import replace
    from app.services.cycle_match_service import CycleMatchService
    _, _, _, cycle, _, replay = match_world(db)
    saved(db, replay)
    saved(db, replace(replay, replay_id='second-game'))
    db.commit()
    original = CycleMatchService.process
    def fail_second(self, db, *, battle_id, replay):
        if replay.replay_id == 'second-game':
            raise RuntimeError('target unavailable')
        return original(self, db, battle_id=battle_id, replay=replay)
    monkeypatch.setattr(CycleMatchService, 'process', fail_second)
    with pytest.raises(RuntimeError, match='unavailable'):
        service().ingest_cycle(db, cycle_id=cycle.id, now=replay.finished_at)
    assert db.query(CycleMatchContribution).count() == 0


def test_unresolved_uuid_source_is_a_durable_dependency_until_original_response_returns(db):
    from app.services.campaign_cycle_store import CampaignCycleStore
    _, _, _, cycle, _, replay = match_world(db)
    match = saved(db, replay)
    original = deepcopy(match.source_payload)
    match.source_payload = {'ReplayId': replay.replay_id, 'Players': []}
    db.flush()
    service().ingest_cycle(db, cycle_id=cycle.id, now=replay.finished_at)
    key = f'source-replay:{match.id}'
    assert cycle.dependencies[key] is False
    with pytest.raises(ValueError, match='Pending'):
        CampaignCycleStore().mark_import_complete(db, cycle_id=cycle.id,
            verified_at=CampaignCycleStore.timeline(cycle).replay_deadline)
    match.source_payload = original
    db.flush()
    service().ingest_cycle(db, cycle_id=cycle.id, now=replay.finished_at)
    assert cycle.dependencies[key] is True
    assert cycle.import_verified_at is None


def test_original_uuid_response_is_not_carried_into_another_replay(db):
    _, _, _, _, _, replay = match_world(db)
    match = saved(db, replay)
    BFMELadderService._apply_api_replay_metadata(match, {
        'ReplayId': 'different-replay', 'Players': [], 'IsValid': True})
    assert 'PublicApiPayload' not in match.source_payload


def test_ingestion_only_calls_accounting_for_territories_with_replay_participants(db, monkeypatch):
    from app.models.cycle_battle import CycleTerritoryBattle
    from app.models.territory import Territory
    from app.services.cycle_match_service import CycleMatchService
    users, home, _, cycle, battle, replay = match_world(db)
    saved(db, replay)
    other_land = Territory(name='Other battle', region='Local', svg_path_data='M0 0', is_playable=True)
    db.add(other_land)
    db.flush()
    db.add(CycleTerritoryBattle(cycle_id=cycle.id, territory_id=other_land.id,
        owner_clan_id=home.id, sides=[{'clan_id': home.id, 'user_ids': [users[0].id]}]))
    db.flush()
    calls = []
    original = CycleMatchService.process
    def account(self, db, *, battle_id, replay):
        calls.append(battle_id)
        assert battle_id == battle.id
        return original(self, db, battle_id=battle_id, replay=replay)
    monkeypatch.setattr(CycleMatchService, 'process', account)
    service().ingest_cycle(db, cycle_id=cycle.id, now=replay.finished_at)
    assert calls == [battle.id]


def test_worker_downloads_and_ingests_before_settling_previously_verified_cycle(db, monkeypatch):
    import asyncio
    from contextlib import nullcontext
    from app.services.campaign_cycle_store import CampaignCycleStore
    from app.services.cycle_startup_service import CycleStartupService
    from tests.test_campaign_cycle_store import START
    import app.services.scheduler_service as scheduler
    _, _, _, cycle, _, replay = match_world(db)
    startup = CycleStartupService().initialize(db, cycle_id=cycle.id, now=START)
    startup.expired_at = CampaignCycleStore.timeline(cycle).preparation_at
    from app.models.campaign import CampaignRuleSet
    from app.core.campaign_rules import default_campaign_rule_values
    db.add(CampaignRuleSet(version=cycle.rule_version, values=default_campaign_rule_values(),
        is_active=True, reason='Local ingestion regression'))
    deadline = CampaignCycleStore.timeline(cycle).replay_deadline
    cycle.import_verified_at = deadline
    db.commit()

    class Ladder:
        async def fetch_and_save_matches(self, db, limit):
            assert cycle.settled_at is None, 'fresh source must be read before settlement'
            saved(db, replay)
            db.commit()
            return 1
    monkeypatch.setattr(scheduler, 'SessionLocal', lambda: nullcontext(db))
    monkeypatch.setattr(scheduler, 'BFMELadderService', Ladder)
    monkeypatch.setattr(scheduler, '_utcnow', lambda: deadline)
    assert asyncio.run(scheduler.CampaignWorker().run_cycle()) == 1
    assert db.query(CycleMatchContribution).count() == 2
    assert cycle.import_verified_at is None and cycle.settled_at is None


def test_missing_duration_is_visible_and_blocks_zero_game_interception_resolution(db, world):
    from tests.test_cycle_interception_service import setup, verify, finish
    replay = setup(db, world)
    saved(db, replay, raw_changes={'duration': None})
    service().ingest_cycle(db, cycle_id=world[3].id, now=replay.finished_at)
    rows = db.query(CycleInterceptionContribution).all()
    assert len(rows) == 2 and {row.reason for row in rows} == {'missing_match_times'}
    verify(db, world)
    with pytest.raises(ValueError, match='pending'):
        finish(db, world)


def test_valid_original_response_can_repair_malformed_stored_json(db):
    _, _, _, _, _, replay = match_world(db)
    match = saved(db, replay)
    response = deepcopy(match.source_payload)
    match.source_payload = ['malformed']
    BFMELadderService._apply_api_replay_metadata(match, response)
    assert service().adapt(match).players[0].uuid == replay.players[0].uuid


def test_corrected_pending_source_time_refreshes_diagnostics_and_revision(db):
    _, _, _, cycle, _, replay = match_world(db)
    match = saved(db, replay)
    service().ingest_cycle(db, cycle_id=cycle.id, now=replay.finished_at)
    revision = cycle.revision
    payload = deepcopy(match.source_payload)
    payload['PublicApiPayload']['date'] += 60000
    match.source_payload = payload
    db.flush()
    service().ingest_cycle(db, cycle_id=cycle.id, now=replay.finished_at + timedelta(minutes=1))
    assert cycle.revision > revision
    assert {row.calculation['started_at'] for row in db.query(CycleMatchContribution)} == {
        (replay.started_at + timedelta(minutes=1)).isoformat()}


def test_unresolved_source_revokes_interception_proof_and_blocks_empty_resolution(db, world):
    from tests.test_cycle_interception_service import setup, verify, finish, service as interception_service, T
    from app.models.cycle_interception import CycleInterception
    replay = setup(db, world)
    verify(db, world)
    match = saved(db, replay)
    match.source_payload = ['malformed canonical source']
    db.flush()
    service().ingest_cycle(db, cycle_id=world[3].id, now=T + timedelta(hours=14, minutes=5))
    record = db.query(CycleInterception).one()
    assert record.verified_at is None and record.completed_at is None
    assert interception_service().settle_ready(db, cycle_id=world[3].id,
        now=T + timedelta(hours=14, minutes=5)) == []
    with pytest.raises(ValueError, match='Pending'):
        verify(db, world)
    with pytest.raises(ValueError):
        finish(db, world)
    assert world[3].dependencies['interception:d'] is False
