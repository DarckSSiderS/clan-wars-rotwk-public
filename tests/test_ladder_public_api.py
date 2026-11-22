import pytest

from app.config import settings
from app.services.ladder_service import BFMELadderService, ReplaySourceError


class _Response:
    status = 200

    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return ""


class _Session:
    def __init__(self):
        self.requests = []

    def get(self, url, *, params, headers):
        self.requests.append(params.copy())
        replay_id = f"{params['arena']}:{params['gamemode']}"
        patch_name = (
            "Ennorath"
            if params["arena"] == settings.LADDER_ENNORATH_ARENA_ID
            else "Patch 2.02"
        )
        return _Response(
            [
                {
                    "replayId": replay_id,
                    "date": 1,
                    "gameName": "RotWK",
                    "gamemode": params["gamemode"],
                    "patchName": patch_name,
                    "players": [],
                }
            ]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize('public_api', [False, True])
async def test_replay_rate_limit_reports_retry_after_without_scan(db, monkeypatch, public_api):
    from app.services import ladder_service

    monkeypatch.setattr(settings, 'LADDER_PUBLIC_API_ENABLED', public_api)
    monkeypatch.setattr(settings, 'LADDER_PUBLIC_API_TOKEN', 'test-token')
    response = _Response([])
    response.status = 429
    response.headers = {'Retry-After': '1800'}
    session = _Session()

    def limited(*args, **kwargs):
        session.requests.append(1)
        return response

    session.get = limited
    service = BFMELadderService()
    with pytest.raises(ReplaySourceError) as error:
        await service._load_api_replays(session, db, None)
    assert isinstance(error.value, ladder_service.ReplayRateLimited)
    assert error.value.retry_after == 1800
    assert session.requests == [1]
    assert service.last_completed_scan is None
    assert service._pending_public_scan is None


@pytest.mark.asyncio
async def test_public_api_loads_both_supported_arenas(db, monkeypatch):
    monkeypatch.setattr(settings, "LADDER_PUBLIC_API_ENABLED", True)
    monkeypatch.setattr(settings, "LADDER_PUBLIC_API_TOKEN", "token")
    monkeypatch.setattr(settings, "LADDER_GAME", "RotWK")
    monkeypatch.setattr(
        settings,
        "LADDER_GAMEMODES",
        "1 versus 1,2 versus 2,3 versus 3,4 versus 4",
    )
    monkeypatch.setattr(settings, "LADDER_API_PATCH_FILTER", "")
    monkeypatch.setattr(
        settings,
        "LADDER_ARENA_ID",
        settings.LADDER_PATCH_202_ARENA_ID,
    )
    session = _Session()

    result = await BFMELadderService()._load_api_replays(
        session,
        db,
        scan_limit=20,
        gamemodes={"1 versus 1", "2 versus 2"},
        start_override_ms=1,
        end_override_ms=2,
        advance_cursor=False,
    )

    requested_arenas = {request["arena"] for request in session.requests}
    assert requested_arenas == {
        settings.LADDER_PATCH_202_ARENA_ID,
        settings.LADDER_ENNORATH_ARENA_ID,
    }
    assert len(session.requests) == 4
    assert len(result) == 4


@pytest.mark.asyncio
async def test_public_api_preserves_explicit_epoch_scan_boundary(db, monkeypatch):
    from app.models.campaign import CampaignSettings
    db.add(CampaignSettings(id=1, replay_cursor_ms=9999999999999))
    db.commit()
    monkeypatch.setattr(settings, 'LADDER_PUBLIC_API_ENABLED', True)
    monkeypatch.setattr(settings, 'LADDER_PUBLIC_API_TOKEN', 'token')
    session = _Session()
    await BFMELadderService()._load_api_replays(session, db, None,
        start_override_ms=0, end_override_ms=2, advance_cursor=False)
    assert all(request['start'] == 0 for request in session.requests)


@pytest.mark.asyncio
async def test_public_api_preserves_saved_zero_checkpoint(db, monkeypatch):
    from app.models.campaign import CampaignSettings
    db.add(CampaignSettings(id=1, replay_cursor_ms=0))
    db.commit()
    monkeypatch.setattr(settings, 'LADDER_PUBLIC_API_ENABLED', True)
    monkeypatch.setattr(settings, 'LADDER_PUBLIC_API_TOKEN', 'token')
    session = _Session()
    await BFMELadderService()._load_api_replays(session, db, None,
        end_override_ms=1800000000000, advance_cursor=False)
    assert all(request['start'] == 0 for request in session.requests)


@pytest.mark.asyncio
@pytest.mark.parametrize('bad_item', [None, {}, {'gameName': 'RotWK',
    'gamemode': '1 versus 1', 'patchName': 'Ennorath', 'date': 1}])
async def test_malformed_public_replay_cannot_certify_complete_scan(db, monkeypatch, bad_item):
    monkeypatch.setattr(settings, 'LADDER_PUBLIC_API_ENABLED', True)
    monkeypatch.setattr(settings, 'LADDER_PUBLIC_API_TOKEN', 'token')

    class Session:
        def get(self, *_args, **_kwargs):
            return _Response([bad_item])

    service = BFMELadderService()
    with pytest.raises(ReplaySourceError, match='replay'):
        await service._load_api_replays(Session(), db, None,
            start_override_ms=1, end_override_ms=2)
    assert service._pending_public_cursor_ms is None
