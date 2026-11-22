"""Исторический рейтинг реплея попадает в новый зачёт без изменения старых очков."""

from copy import deepcopy
from datetime import timedelta
from urllib.parse import quote

import pytest

from app.services.cycle_arena_ingestion_service import CycleArenaIngestionService
from app.services.ladder_service import BFMELadderService
from tests.test_cycle_arena_ingestion import saved
from tests.test_cycle_match_service import match_world


def html_for(raw):
    cards = []
    for player in raw['players']:
        team, win = player['team'], player['isWinner']
        before, after, delta = (1200, 1210, '+10') if win else (1500, 1490, '-10')
        cards.append(f'''<div><div><span>Team {team}</span> · <span>{'Winners' if win else 'Losers'}</span></div>
          <div><span><a href="/u/OtherName">Совсем другой ник</a></span>
          <span><span>rank {player['oldRank']} → {player['newRank']}</span>
          <span class="rx"><button class="rx-btn">{delta} ELO</button><span class="rx-pop">
          <ul><li>Rating before: {before}</li><li>Rating after: {after}</li></ul></span></span></span></div></div>''')
    return (f'<div><h1>Map</h1><p>RotWK · {raw["patchName"]} · {raw["gamemode"]}</p></div>'
            f'<a href="/api/replays/download?replayId={quote(raw["replayId"], safe="")}">Download</a>' + ''.join(cards))


def evidence(raw):
    from app.services.arena_replay_rating_service import ArenaReplayRatingService
    result = ArenaReplayRatingService.parse(html_for(raw), raw)
    assert result is not None
    return result


class Response:
    def __init__(self, html, status=200):
        self.html, self.status = html, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def text(self):
        return self.html


class Session:
    def __init__(self, html='', status=200):
        self.html, self.status, self.requests = html, status, []

    def get(self, url, **kwargs):
        self.requests.append(url)
        assert 'Authorization' not in kwargs.get('headers', {})
        return Response(self.html, self.status)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


def test_adapter_uses_only_uuid_bound_replay_before_not_rank_or_current_rating(db):
    _, _, _, _, _, facts = match_world(db)
    match = saved(db, facts)
    raw = match.source_payload['PublicApiPayload']
    match.source_payload = {**match.source_payload, 'ArenaReplayRatings': evidence(raw)}
    adapted = CycleArenaIngestionService.adapt(match)
    assert {p.uuid: (p.elo, p.historical, p.rating_patch) for p in adapted.players} == {
        p['uuid']: (1200 if p['isWinner'] else 1500, True, 'ennorath') for p in raw['players']}
    assert match.winner_elo == match.loser_elo == 9999
    assert match.rating_source == 'bfmeladder_current'


def test_metadata_refresh_keeps_matching_evidence_but_rejects_changed_match_facts(db):
    _, _, _, _, _, facts = match_world(db)
    match = saved(db, facts)
    raw = deepcopy(match.source_payload['PublicApiPayload'])
    value = evidence(raw)
    match.source_payload = {**match.source_payload, 'ArenaReplayRatings': value}
    raw['downloads'] = 123
    _, normalized = BFMELadderService._normalize_public_replay(raw)
    BFMELadderService._apply_api_replay_metadata(match, normalized)
    assert match.source_payload['ArenaReplayRatings'] == value
    raw['players'][0]['oldRank'] += 1
    _, normalized = BFMELadderService._normalize_public_replay(raw)
    BFMELadderService._apply_api_replay_metadata(match, normalized)
    assert 'ArenaReplayRatings' not in match.source_payload
    assert all(p.elo is None for p in CycleArenaIngestionService.adapt(match).players)


@pytest.mark.asyncio
async def test_known_cycle_match_is_enriched_and_pending_contributions_are_resumed_by_uuid(db):
    users, _, _, cycle, battle, facts = match_world(db)
    match = saved(db, facts)
    loader, importer = BFMELadderService(), CycleArenaIngestionService()
    importer.ingest_cycle(db, cycle_id=cycle.id, now=facts.finished_at + timedelta(minutes=1))
    raw = deepcopy(match.source_payload['PublicApiPayload'])
    _, replay = loader._normalize_public_replay(raw)
    session = Session(html_for(raw))
    users[2].username = 'Новое имя'
    await loader._enrich_cycle_replay_ratings(session, db, [(match.match_id, replay)], {match.match_id: match})
    assert replay['ArenaReplayRatings']
    assert len(session.requests) == 1
    loader._apply_api_replay_metadata(match, replay)
    importer.ingest_cycle(db, cycle_id=cycle.id, now=facts.finished_at + timedelta(minutes=2))
    from app.models.cycle_battle import CycleMatchContribution
    rows = db.query(CycleMatchContribution).filter_by(battle_id=battle.id).all()
    assert len(rows) == 2 and all(row.counted for row in rows)
    assert {row.calculation['historical_elo'] for row in rows} == {'1200', '1500'}
    await loader._enrich_cycle_replay_ratings(session, db, [(match.match_id, replay)], {match.match_id: match})
    assert len(session.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('status,html', [(503, ''), (200, '<h1>Incomplete response</h1>')])
async def test_rating_page_failure_remains_retryable_without_default_elo(db, status, html):
    _, _, _, _, _, facts = match_world(db)
    match = saved(db, facts)
    _, replay = BFMELadderService._normalize_public_replay(match.source_payload['PublicApiPayload'])
    loader = BFMELadderService()
    assert not await loader._enrich_replay_ratings(Session(html, status), replay)
    assert 'ArenaReplayRatings' not in replay
    assert await loader._enrich_replay_ratings(Session(html_for(replay['PublicApiPayload'])), replay)
    assert replay['ArenaReplayRatings']


@pytest.mark.asyncio
async def test_unrelated_known_history_does_not_trigger_bulk_detail_download(db):
    _, _, _, cycle, _, facts = match_world(db)
    match = saved(db, facts)
    raw = deepcopy(match.source_payload['PublicApiPayload'])
    raw['date'] -= 30 * 86400000
    _, replay = BFMELadderService._normalize_public_replay(raw)
    session = Session()
    await BFMELadderService()._enrich_cycle_replay_ratings(session, db, [(match.match_id, replay)], {match.match_id: match})
    assert session.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['html_refresh', 'absent_from_api'])
async def test_pending_saved_rating_is_retried_independently_of_fresh_api_listing(db, source):
    from app.services.arena_replay_rating_service import ArenaReplayRatingService
    _, _, _, _, _, facts = match_world(db)
    match = saved(db, facts)
    raw = deepcopy(match.source_payload['PublicApiPayload'])
    _, replay = BFMELadderService._normalize_public_replay(raw)
    replay.pop('PublicApiPayload')
    items = [(match.match_id, replay)] if source == 'html_refresh' else []
    known = {match.match_id: match} if items else {}
    session = Session(html_for(raw))
    await BFMELadderService()._enrich_cycle_replay_ratings(session, db, items, known)
    assert len(session.requests) == 1
    assert ArenaReplayRatingService.read(match.source_payload.get('ArenaReplayRatings'), raw)
    if items:
        BFMELadderService._apply_api_replay_metadata(match, replay)
        assert ArenaReplayRatingService.read(match.source_payload.get('ArenaReplayRatings'), raw)
    await BFMELadderService()._enrich_cycle_replay_ratings(session, db, items, known)
    assert len(session.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('known', [False, True])
async def test_full_loader_persists_replay_evidence_and_retries_known_pending_game(db, monkeypatch, known):
    import app.services.ladder_service as module
    from app.config import settings
    from app.models.match import Match
    from app.models.cycle_battle import CycleMatchContribution

    users, _, _, cycle, battle, facts = match_world(db)
    match = saved(db, facts)
    raw = deepcopy(match.source_payload['PublicApiPayload'])
    if not known:
        db.delete(match)
        db.flush()
    else:
        match.rating_patch_family = 'ennorath'
    for player, user in zip(raw['players'], users[2:4]):
        player['displayName'] = user.username
    session = Session(html_for(raw), 503 if known else 200)
    loader = BFMELadderService()

    async def load(*_, **kwargs):
        return [loader._normalize_public_replay(deepcopy(raw))]

    async def no_external_io(*_, **kwargs):
        return None

    monkeypatch.setattr(settings, 'PROXY_URL', '')
    monkeypatch.setattr(settings, 'REPLAY_BACKFILL_PER_SYNC', 0)
    monkeypatch.setattr(module.aiohttp, 'TCPConnector', lambda: None)
    monkeypatch.setattr(module.aiohttp, 'ClientSession', lambda **kwargs: session)
    monkeypatch.setattr(loader, '_load_api_replays', load)
    monkeypatch.setattr(loader, '_capture_team_ratings', no_external_io)
    monkeypatch.setattr(module.ReplayStorageService, 'download_match', no_external_io)
    monkeypatch.setattr(module.MapPreviewStorageService, 'download_match', no_external_io)
    monkeypatch.setattr(module.asyncio, 'sleep', no_external_io)
    end = int((facts.finished_at + timedelta(minutes=10)).timestamp() * 1000)
    importer = CycleArenaIngestionService()
    await loader.fetch_and_save_matches_from_api(db, end_override_ms=end)
    importer.ingest_cycle(db, cycle_id=cycle.id, now=facts.finished_at + timedelta(minutes=1))
    rows = db.query(CycleMatchContribution).filter_by(battle_id=battle.id).all()
    assert len(rows) == 2
    if known:
        assert all(row.reason == 'missing_historical_elo' for row in rows)
        session.status = 200
        await loader.fetch_and_save_matches_from_api(db, end_override_ms=end)
        importer.ingest_cycle(db, cycle_id=cycle.id, now=facts.finished_at + timedelta(minutes=2))
    match = db.query(Match).filter_by(match_id=facts.replay_id).one()
    assert match.source_payload['ArenaReplayRatings']
    assert all(row.counted for row in rows)
    assert {row.calculation['historical_elo'] for row in rows} == {'1200', '1500'}
    before = [(row.id, row.points) for row in rows]
    calls = len(session.requests)
    await loader.fetch_and_save_matches_from_api(db, end_override_ms=end)
    importer.ingest_cycle(db, cycle_id=cycle.id, now=facts.finished_at + timedelta(minutes=3))
    assert [(row.id, row.points) for row in rows] == before
    assert len(session.requests) == calls
    assert db.query(CycleMatchContribution).filter_by(battle_id=battle.id).count() == 2
