from datetime import datetime, timezone

import pytest

from app.config import settings
from app.services.ladder_service import BFMELadderService, ReplaySourceError
from tests.test_ladder_public_api import _Response


@pytest.fixture
def empty_source(monkeypatch):
    calls = []
    monkeypatch.setattr(settings, 'LADDER_PUBLIC_API_ENABLED', True)
    monkeypatch.setattr(settings, 'LADDER_PUBLIC_API_TOKEN', 'test-token-not-for-evidence')
    monkeypatch.setattr(settings, 'LADDER_GAME', 'RotWK')
    monkeypatch.setattr(settings, 'LADDER_GAMEMODES', '1 versus 1,2 versus 2,3 versus 3,4 versus 4')
    monkeypatch.setattr(settings, 'LADDER_API_PATCH_FILTER', '')
    monkeypatch.setattr(settings, 'LADDER_PATCH_202_ARENA_ID', 'arena-202')
    monkeypatch.setattr(settings, 'LADDER_ENNORATH_ARENA_ID', 'arena-ennorath')
    monkeypatch.setattr(settings, 'LADDER_ARENA_ID', 'arena-202')
    monkeypatch.setattr(settings, 'PROXY_URL', '')

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def get(self, url, *, params, headers):
            calls.append(params.copy())
            return _Response([])

    import app.services.ladder_service as module
    monkeypatch.setattr(module, 'utc_now', lambda: datetime(2028, 1, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(module.aiohttp, 'TCPConnector', lambda: None)
    monkeypatch.setattr(module.aiohttp, 'ClientSession', lambda **kwargs: Session())
    return calls, Session


@pytest.mark.asyncio
async def test_completed_scan_is_exposed_only_after_all_scopes_and_database_commit(db, empty_source):
    calls, _ = empty_source
    service = BFMELadderService()
    await service.fetch_and_save_matches_from_api(db, start_override_ms=1, end_override_ms=1800000000000)
    evidence = getattr(service, 'last_completed_scan', None)
    assert evidence is not None
    assert evidence.covered_start == datetime.fromtimestamp(.001, tz=timezone.utc)
    assert evidence.covered_end == datetime.fromtimestamp(1800000000, tz=timezone.utc)
    assert len(calls) == 8
    assert 'test-token' not in repr(evidence)


@pytest.mark.asyncio
async def test_download_without_persistence_does_not_certify_scan(db, empty_source):
    _, Session = empty_source
    service = BFMELadderService()
    await service._load_api_replays(Session(), db, None, start_override_ms=1, end_override_ms=2)
    assert getattr(service, 'last_completed_scan', None) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('restricted', ['one_mode', 'partial_import', 'patch_filter', 'missing_arena'])
async def test_incomplete_scope_never_claims_full_cycle_coverage(db, empty_source, monkeypatch, restricted):
    kwargs = {}
    if restricted == 'one_mode':
        monkeypatch.setattr(settings, 'LADDER_GAMEMODES', '1 versus 1')
    elif restricted == 'partial_import':
        kwargs['advance_cursor'] = False
    elif restricted == 'patch_filter':
        monkeypatch.setattr(settings, 'LADDER_API_PATCH_FILTER', 'Ennorath')
    else:
        monkeypatch.setattr(settings, 'LADDER_ENNORATH_ARENA_ID', '')
    service = BFMELadderService()
    await service.fetch_and_save_matches_from_api(db, start_override_ms=1, end_override_ms=1800000000000, **kwargs)
    assert getattr(service, 'last_completed_scan', None) is None


@pytest.mark.asyncio
async def test_failed_scan_cannot_reuse_previous_success(db, empty_source, monkeypatch):
    service = BFMELadderService()
    await service.fetch_and_save_matches_from_api(db, start_override_ms=1, end_override_ms=1800000000000)
    assert getattr(service, 'last_completed_scan', None) is not None

    async def fail(*args, **kwargs):
        raise ReplaySourceError('Ошибка страницы Арены')

    monkeypatch.setattr(service, '_load_api_replays', fail)
    with pytest.raises(ReplaySourceError):
        await service.fetch_and_save_matches_from_api(db, start_override_ms=1, end_override_ms=1800000000001)
    assert service.last_completed_scan is None


@pytest.mark.asyncio
async def test_disabled_scoring_patch_cannot_certify_its_matches_as_absent(db, empty_source):
    from app.models.campaign import CampaignSettings
    db.add(CampaignSettings(id=1, ennorath_enabled=False, patch_202_enabled=True))
    db.commit()
    service = BFMELadderService()
    await service.fetch_and_save_matches_from_api(db, start_override_ms=1, end_override_ms=1800000000000)
    assert service.last_completed_scan is None


@pytest.mark.asyncio
async def test_failed_commit_does_not_publish_completed_scan(db, empty_source, monkeypatch):
    from app.services.campaign_settings_service import CampaignSettingsService
    from app.services.campaign_rule_service import CampaignRuleService
    CampaignSettingsService().get_or_create(db)
    CampaignRuleService().get_active(db)
    db.commit()

    def fail():
        raise RuntimeError('Не удалось сохранить загрузку')

    monkeypatch.setattr(db, 'commit', fail)
    service = BFMELadderService()
    with pytest.raises(RuntimeError):
        await service.fetch_and_save_matches_from_api(db, start_override_ms=1, end_override_ms=1800000000000)
    assert getattr(service, 'last_completed_scan', None) is None


@pytest.mark.asyncio
async def test_failed_last_scope_does_not_certify_first_seven_successes(db, empty_source, monkeypatch):
    _, Session = empty_source
    attempts = []

    def get(self, url, *, params, headers):
        attempts.append(params.copy())
        if len(attempts) == 8:
            raise ReplaySourceError('Последний запрос Арены завершился ошибкой')
        return _Response([])

    monkeypatch.setattr(Session, 'get', get)
    service = BFMELadderService()
    with pytest.raises(ReplaySourceError):
        await service.fetch_and_save_matches_from_api(db, start_override_ms=1, end_override_ms=1800000000000)
    assert len(attempts) == 8
    assert service.last_completed_scan is None


@pytest.mark.asyncio
async def test_unprocessed_replay_cannot_turn_successful_requests_into_empty_scan(db, empty_source, monkeypatch):
    _, Session = empty_source
    replay = dict(replayId='missing-result', date=1700000000000, gameName='RotWK',
        gamemode='1 versus 1', patchName='Ennorath', duration='00:10:00',
        players=[dict(uuid='00000000-0000-0000-0000-000000000001', team=1),
                 dict(uuid='00000000-0000-0000-0000-000000000002', team=2)])
    monkeypatch.setattr(Session, 'get', lambda *args, **kwargs: _Response([replay]))
    service = BFMELadderService()
    with pytest.raises(ReplaySourceError, match='unprocessed'):
        await service.fetch_and_save_matches_from_api(db, start_override_ms=1, end_override_ms=1800000000000)
    assert service.last_completed_scan is None


@pytest.mark.asyncio
@pytest.mark.parametrize('duration, winner', [('00:00:00', False), ('00:00:01', False), ('00:00:00', None)])
async def test_cancelled_public_game_does_not_block_full_scan(db, empty_source, monkeypatch, duration, winner):
    from app.models.campaign import ReplaySyncState

    _, Session = empty_source
    player = dict(uuid='00000000-0000-0000-0000-000000000001', team=1)
    if winner is not None:
        player['isWinner'] = winner
    replay = dict(replayId='cancelled', date=1700000000000, gameName='RotWK',
                  gamemode='1 versus 1', patchName='Ennorath', duration=duration, players=[player])
    monkeypatch.setattr(Session, 'get', lambda *args, **kwargs: _Response([replay]))
    service = BFMELadderService()
    kwargs = dict(start_override_ms=1, end_override_ms=1800000000000)
    if duration != '00:00:00' or winner is None:
        with pytest.raises(ReplaySourceError, match='unprocessed'):
            await service.fetch_and_save_matches_from_api(db, **kwargs)
        assert service.last_completed_scan is None
        return
    assert await service.fetch_and_save_matches_from_api(db, **kwargs) == 0
    assert service.last_completed_scan.replay_ids == {'cancelled'}
    assert db.get(ReplaySyncState, 'cancelled').status == 'skipped'


@pytest.mark.asyncio
async def test_query_started_before_requested_end_cannot_be_certified_by_late_response(db, empty_source, monkeypatch):
    import app.services.ladder_service as module
    _, Session = empty_source
    clock = {'now': datetime(2026, 1, 1, tzinfo=timezone.utc)}

    def get(*args, **kwargs):
        clock['now'] = datetime(2028, 1, 1, tzinfo=timezone.utc)
        return _Response([])

    monkeypatch.setattr(module, 'utc_now', lambda: clock['now'])
    monkeypatch.setattr(Session, 'get', get)
    service = BFMELadderService()
    await service.fetch_and_save_matches_from_api(db, start_override_ms=1, end_override_ms=1800000000000)
    assert service.last_completed_scan is None


@pytest.mark.asyncio
async def test_replay_without_patch_cannot_disappear_from_certified_scan(db, empty_source, monkeypatch):
    _, Session = empty_source
    raw = dict(replayId='without-patch', date=1700000000000,
        gameName='RotWK', gamemode='1 versus 1', players=[])
    monkeypatch.setattr(Session, 'get', lambda *args, **kwargs: _Response([raw]))
    service = BFMELadderService()
    with pytest.raises(ReplaySourceError):
        await service.fetch_and_save_matches_from_api(db, start_override_ms=1, end_override_ms=1800000000000)
    assert service.last_completed_scan is None
