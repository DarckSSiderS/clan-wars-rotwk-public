from datetime import timedelta

import pytest

from app.core.time import utc_now, as_utc
from app.models.campaign import CampaignSettings
from app.services.ladder_service import BFMELadderService, ReplaySourceError
from app.config import settings
from test_war_deployment_scoring import _active_v3_war


def test_downtime_match_counts_before_finalization_without_duplicates(db, monkeypatch):
    from app.models.worker import WorkerHeartbeat
    from app.models.war import ClanWarMatchResult
    from app.services.war_service import ClanWarService
    from test_war_deployment_scoring import _match

    war, _, attackers, _, defenders = _active_v3_war(db)
    war.ends_at = as_utc(war.started_at) + timedelta(minutes=10)
    resumed_at = as_utc(war.ends_at) + timedelta(hours=6)
    db.commit()
    monkeypatch.setattr("app.services.war_service.utc_now", lambda: resumed_at)
    service = ClanWarService()
    assert service.complete_expired_wars(db) == 0

    result = _match(db, war, attackers[:1], defenders[:1], "during-downtime")
    assert result.is_counted is True
    assert result.winner_total_points > 0
    match = result.match
    service.record_match_result(db, match.winner_player, match.loser_player, match.match_date, match)
    assert db.query(ClanWarMatchResult).filter_by(war_id=war.id).count() == 1

    db.add(WorkerHeartbeat(worker_name="campaign", replay_synced_through_at=resumed_at))
    db.commit()
    assert service.complete_expired_wars(db) == 1
    assert war.winner_clan_id == war.attacking_clan_id


@pytest.mark.asyncio
async def test_html_recovery_scans_entire_downtime_and_commits_checkpoint(db, monkeypatch):
    old_cursor = int((utc_now() - timedelta(days=5)).timestamp() * 1000)
    campaign = CampaignSettings(id=1, replay_cursor_ms=old_cursor)
    db.add(campaign)
    db.commit()
    service = BFMELadderService()
    captured = {}
    imported = []

    async def load(_session, _db, scan_limit, **kwargs):
        service._pending_public_cursor_ms = None
        captured.update(kwargs, scan_limit=scan_limit)
        return [(str(index), {
            "GameName": "RotWK", "GamemodeName": "1 versus 1",
            "PatchName": "Patch 2.02", "IsValid": True,
            "Players": [{"DisplayName": "A", "IsWinner": True}, {"DisplayName": "B", "IsWinner": False}],
        }) for index in range(24)]

    async def players(*args):
        return [("A", "elves", None)], [("B", "men", None)]

    async def ratings(*args):
        return None

    async def no_sleep(*args):
        pass

    monkeypatch.setattr(settings, "LADDER_PUBLIC_API_ENABLED", False)
    monkeypatch.setattr(service, "_load_api_replays", load)
    monkeypatch.setattr(service, "_fetch_replay_players", players)
    monkeypatch.setattr(service, "_capture_team_ratings", ratings)
    monkeypatch.setattr(service, "_build_participant_rows", lambda *args: [])
    monkeypatch.setattr(service, "_save_match_to_db", lambda **kwargs: imported.append(kwargs["match_id"]) or True)
    monkeypatch.setattr("app.services.ladder_service.asyncio.sleep", no_sleep)
    assert await service.fetch_and_save_matches_from_api(db, new_limit=15) == 24
    assert len(imported) == 24
    assert captured["scan_limit"] is None
    assert captured["paginate_html"] is True
    assert captured["start_override_ms"] == old_cursor - settings.LADDER_SYNC_OVERLAP_MINUTES * 60000
    db.refresh(campaign)
    assert campaign.replay_cursor_ms == captured["end_override_ms"]


@pytest.mark.asyncio
async def test_failed_downtime_scan_keeps_previous_checkpoint(db, monkeypatch):
    campaign = CampaignSettings(id=1, replay_cursor_ms=123)
    db.add(campaign)
    db.commit()
    service = BFMELadderService()

    async def fail(*args, **kwargs):
        raise ReplaySourceError("page 2 unavailable")

    monkeypatch.setattr(service, "_load_api_replays", fail)
    with pytest.raises(ReplaySourceError):
        await service.fetch_and_save_matches_from_api(db)
    db.refresh(campaign)
    assert campaign.replay_cursor_ms == 123


@pytest.mark.asyncio
@pytest.mark.parametrize("ends_in_minutes", [-1, 120])
async def test_pending_war_requests_complete_window_without_normal_scan_limits(db, monkeypatch, ends_in_minutes):
    war, *_ = _active_v3_war(db)
    war.started_at = utc_now() - timedelta(hours=60)
    war.ends_at = utc_now() + timedelta(minutes=ends_in_minutes)
    db.commit()
    service = BFMELadderService()
    captured = {}

    async def load(_session, _db, scan_limit, **kwargs):
        captured.update(kwargs, scan_limit=scan_limit)
        service._pending_public_cursor_ms = None
        return []

    monkeypatch.setattr(service, "_load_api_replays", load)
    assert await service.fetch_and_save_matches_from_api(db, new_limit=1) == 0
    assert captured["scan_limit"] is None
    assert captured["paginate_html"] is True
    assert captured["start_override_ms"] == int(as_utc(war.started_at).timestamp() * 1000)


@pytest.mark.asyncio
async def test_partial_import_raises_and_does_not_advance_cursor(db, monkeypatch):
    campaign = CampaignSettings(id=1, replay_cursor_ms=100)
    db.add(campaign)
    db.commit()
    service = BFMELadderService()

    async def load(*_args, **_kwargs):
        service._pending_public_cursor_ms = 999
        return [("missing-players", {
            "GameName": "RotWK", "GamemodeName": "1 versus 1",
            "PatchName": "Patch 2.02", "PatchId": "official-2:9.6.5",
            "Players": [], "IsValid": True,
        })]

    monkeypatch.setattr(service, "_load_api_replays", load)
    with pytest.raises(ReplaySourceError, match="unprocessed"):
        await service.fetch_and_save_matches_from_api(db)
    db.refresh(campaign)
    assert campaign.replay_cursor_ms == 100


@pytest.mark.asyncio
@pytest.mark.parametrize('settled', [False, True])
async def test_cycle_recovery_keeps_unsettled_battle_window_in_scan(db, monkeypatch, settled):
    from tests.test_cycle_match_service import match_world
    from app.services.campaign_cycle_store import CampaignCycleStore

    _, _, _, cycle, _, _ = match_world(db)
    timeline = CampaignCycleStore.timeline(cycle)
    resumed_at = timeline.replay_deadline + timedelta(days=4)
    if settled:
        cycle.settled_at = timeline.replay_deadline
    cursor = int((resumed_at - timedelta(minutes=1)).timestamp() * 1000)
    campaign = CampaignSettings(id=1, replay_cursor_ms=cursor)
    db.add(campaign)
    db.commit()
    captured = {}
    service = BFMELadderService()

    async def load(_session, _db, scan_limit, **kwargs):
        service._pending_public_cursor_ms = None
        captured.update(kwargs, scan_limit=scan_limit)
        return []

    monkeypatch.setattr(service, '_load_api_replays', load)
    assert await service.fetch_and_save_matches_from_api(db,
        end_override_ms=int(resumed_at.timestamp() * 1000)) == 0
    expected = (cursor - settings.LADDER_SYNC_OVERLAP_MINUTES * 60000 if settled
                else int(timeline.battle_at.timestamp() * 1000))
    assert captured['start_override_ms'] == expected
    assert captured['paginate_html'] is True
    assert cycle.import_verified_at is None


@pytest.mark.asyncio
async def test_missing_checkpoint_recovers_from_last_saved_match(db, monkeypatch):
    from app.models.match import Match

    end = utc_now()
    last = end - timedelta(days=9)
    db.add_all([
        Match(match_id='last-before-offline', winner_player='A', loser_player='B',
            winner_faction='elves', loser_faction='men', match_date=last, game_name='RotWK'),
        Match(match_id='future-not-a-checkpoint', winner_player='A', loser_player='B',
            winner_faction='elves', loser_faction='men', match_date=end + timedelta(days=1)),
        Match(match_id='live-not-a-checkpoint', winner_player='A', loser_player='B',
            winner_faction='elves', loser_faction='men', match_date=end, is_live=True),
    ])
    db.commit()
    service = BFMELadderService()
    captured = {}

    async def load(_session, _db, scan_limit, **kwargs):
        service._pending_public_cursor_ms = None
        captured.update(kwargs)
        return []

    monkeypatch.setattr(service, '_load_api_replays', load)
    await service.fetch_and_save_matches_from_api(db, end_override_ms=int(end.timestamp() * 1000))
    assert captured['start_override_ms'] == int(last.timestamp() * 1000) - settings.LADDER_SYNC_OVERLAP_MINUTES * 60000
