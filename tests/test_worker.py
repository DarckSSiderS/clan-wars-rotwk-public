import asyncio
from contextlib import nullcontext
from datetime import timedelta
from inspect import getsource

import pytest

import app.main
import app.services.scheduler_service as scheduler_module
from app.config import settings
from app.models.war import ClanWar
from app.models.worker import WorkerHeartbeat
from app.services.scheduler_service import CampaignWorker, WorkerStatusService
from app.services.worker_alert_service import WorkerAlertService
from app.core.time import utc_now


def test_api_import_does_not_modify_database_schema():
    source = getsource(app.main)
    assert "ALTER TABLE" not in source
    assert "create_all" not in source
    assert "CampaignWorker(" not in source


def test_worker_status_uses_persisted_heartbeat(db):
    heartbeat = WorkerHeartbeat(
        worker_name="campaign",
        started_at=utc_now() - timedelta(minutes=5),
        heartbeat_at=utc_now(),
        last_success_at=utc_now(),
        last_duration_ms=125,
    )
    db.add(heartbeat)
    db.commit()

    status = WorkerStatusService().get_status(db)

    assert status["is_running"] is True
    assert status["status"] == "running"
    assert status["interval_seconds"] == settings.SCHEDULER_UPDATE_INTERVAL
    assert status["last_duration_ms"] == 125


def test_worker_uses_nearest_persisted_war_deadline_after_restart(db):
    now = utc_now()
    war = ClanWar(
        territory_id=100,
        attacking_clan_id=10,
        defending_clan_id=11,
        war_type="territory_attack",
        status="active",
        ends_at=now + timedelta(seconds=37),
    )
    db.add(war)
    db.commit()

    restarted_worker = CampaignWorker(interval_seconds=600)
    delay = restarted_worker._next_war_wake_delay(db, now=now)

    assert delay == min(600, 37 + settings.WAR_REPLAY_GRACE_MINUTES * 60)
    war.status = "completed"
    db.commit()
    assert restarted_worker._next_war_wake_delay(db, now=now) == 600


def test_worker_deadline_loop_completes_without_waiting_for_sync_cycle(db, monkeypatch):
    monkeypatch.setattr(scheduler_module, 'SessionLocal', lambda: nullcontext(db))
    worker = CampaignWorker(interval_seconds=600)
    completed = []
    worker._next_war_wake_delay = lambda db: 0.01

    async def complete_due_wars():
        completed.append(True)
        worker.stop()
        return 1

    worker._complete_due_wars = complete_due_wars
    asyncio.run(asyncio.wait_for(worker._run_war_deadline_loop(), timeout=1))

    assert completed == [True]


def test_war_deadline_requests_replay_sync_without_waiting_normal_interval(db, monkeypatch):
    monkeypatch.setattr(settings, 'WAR_REPLAY_GRACE_MINUTES', 5)
    now = utc_now()
    db.add(ClanWar(territory_id=100, attacking_clan_id=10, war_type='neutral_capture', status='active', ends_at=now - timedelta(minutes=5, seconds=1)))
    db.add(WorkerHeartbeat(worker_name='campaign', replay_synced_through_at=now - timedelta(minutes=2)))
    db.commit()
    worker = CampaignWorker(interval_seconds=600)
    worker._request_due_replay_sync(db, now=now)
    assert worker._sync_requested.is_set()
    worker._sync_requested.clear()
    db.get(WorkerHeartbeat, 'campaign').replay_synced_through_at = now
    db.commit()
    worker._request_due_replay_sync(db, now=now)
    assert not worker._sync_requested.is_set()


def test_requested_sync_wakes_sleep_and_stop_still_works():
    async def check():
        worker = CampaignWorker()
        worker._sync_requested.set()
        assert not await asyncio.wait_for(worker._wait_or_stop(600, wake_event=worker._sync_requested), timeout=1)
        worker._sync_requested.clear()
        worker.stop()
        assert await asyncio.wait_for(worker._wait_or_stop(600, wake_event=worker._sync_requested), timeout=1)
    asyncio.run(check())


def test_worker_completes_wars_only_after_successful_network_sync(db, monkeypatch):
    events = []
    worker = CampaignWorker(interval_seconds=600)

    async def complete_due_wars():
        events.append("wars")
        return 0

    class FakeLadderService:
        async def fetch_and_save_matches(self, db, limit):
            events.append("ladder")
            return 0

    class FakeBackfillService:
        async def process_pending(self, db):
            events.append("backfill")
            return 0

    class FakeEconomyService:
        def settle_all(self, db):
            events.append("economy")

    worker._complete_due_wars = complete_due_wars
    monkeypatch.setattr(
        scheduler_module,
        "SessionLocal",
        lambda: nullcontext(db),
    )
    monkeypatch.setattr(
        scheduler_module,
        "BFMELadderService",
        FakeLadderService,
    )
    monkeypatch.setattr(
        scheduler_module,
        "ArenaMatchBackfillService",
        FakeBackfillService,
    )
    monkeypatch.setattr(
        scheduler_module,
        "ClanEconomyService",
        FakeEconomyService,
    )

    asyncio.run(worker.run_cycle())

    assert events == ["ladder", "economy", "wars", "backfill"]


def test_worker_respects_rate_limit_without_stopping_runtime(db, monkeypatch):
    from app.services import ladder_service

    clock = [utc_now()]
    events = []

    class Runtime:
        def tick(self, db, *, now, allow_settlement=True):
            events.append('runtime')
            return True

    class Ladder:
        async def fetch_and_save_matches(self, db, limit):
            events.append('replays')
            raise ladder_service.ReplayRateLimited('1800')

    monkeypatch.setattr(scheduler_module, 'SessionLocal', lambda: nullcontext(db))
    monkeypatch.setattr(scheduler_module, '_utcnow', lambda: clock[0])
    monkeypatch.setattr(scheduler_module, 'CycleRuntimeService', Runtime)
    monkeypatch.setattr(scheduler_module, 'BFMELadderService', Ladder)
    worker = CampaignWorker(interval_seconds=600)

    asyncio.run(worker.run_cycle())
    clock[0] += timedelta(minutes=10)
    asyncio.run(worker.run_cycle())
    heartbeat = db.get(WorkerHeartbeat, 'campaign')
    assert heartbeat.heartbeat_at.replace(tzinfo=clock[0].tzinfo) == clock[0]
    assert heartbeat.replay_synced_through_at is None
    assert '429' in heartbeat.last_error
    assert events == ['runtime', 'replays', 'runtime']
    clock[0] += timedelta(minutes=20)
    asyncio.run(worker.run_cycle())
    assert events[-2:] == ['runtime', 'replays']


def test_cycle_mode_worker_runs_new_runtime_without_legacy_payouts(db, monkeypatch):
    events = []

    class Runtime:
        def tick(self, db, *, now, allow_settlement=True):
            events.append('cycle')
            return True

    class Ladder:
        async def fetch_and_save_matches(self, db, limit):
            events.append('ladder')
            return 0

    class Backfill:
        async def process_pending(self, db):
            events.append('backfill')
            return 0

    class Intake:
        def ingest_pending(self, db, *, now):
            events.append('ingest')
            return {'source_errors': 0, 'pending_receipts': 0}

    class ForbiddenLegacyEconomy:
        def settle_all(self, db):
            pytest.fail('Cycle mode must not pay legacy income')

    monkeypatch.setattr(scheduler_module, 'SessionLocal', lambda: nullcontext(db))
    monkeypatch.setattr(scheduler_module, 'CycleRuntimeService', Runtime, raising=False)
    monkeypatch.setattr(scheduler_module, 'BFMELadderService', Ladder)
    monkeypatch.setattr(scheduler_module, 'ArenaMatchBackfillService', Backfill)
    monkeypatch.setattr(scheduler_module, 'CycleArenaIngestionService', Intake, raising=False)
    monkeypatch.setattr(scheduler_module, 'ClanEconomyService', ForbiddenLegacyEconomy)
    worker = CampaignWorker()

    async def forbidden_legacy_wars():
        pytest.fail('Cycle mode must not finalize legacy wars')

    worker._complete_due_wars = forbidden_legacy_wars
    asyncio.run(worker.run_cycle())
    assert events == ['cycle', 'ladder', 'ingest', 'cycle', 'backfill']


def test_worker_alert_payload_is_safe_and_webhook_failure_is_nonfatal(monkeypatch):
    payloads = []
    service = WorkerAlertService(webhook_url="https://alerts.example.test/hook")

    async def capture(payload):
        payloads.append(payload)
        return True

    monkeypatch.setattr(service, "_post", capture)
    sent = asyncio.run(service.notify_failure(consecutive_failures=3, occurred_at=utc_now()))
    recovered = asyncio.run(service.notify_recovery(occurred_at=utc_now()))

    assert sent is True
    assert recovered is True
    assert payloads[0]["code"] == "campaign_worker_cycle_failed"
    assert payloads[0]["consecutive_failures"] == 3
    assert payloads[1]["code"] == "campaign_worker_recovered"
    assert "message" not in payloads[0]
    assert "detail" not in payloads[0]
    assert "traceback" not in payloads[0]

    async def broken(_payload):
        raise OSError("webhook unavailable")

    monkeypatch.setattr(service, "_post", broken)
    assert asyncio.run(service.notify_failure(consecutive_failures=4, occurred_at=utc_now())) is False


def test_worker_persists_failure_streak_and_notifies_recovery(db, monkeypatch):
    notifications = []
    worker = CampaignWorker(interval_seconds=600)

    class FakeAlerts:
        async def notify_failure(self, *, consecutive_failures, occurred_at):
            notifications.append(("failure", consecutive_failures, occurred_at))
            return True

        async def notify_recovery(self, *, occurred_at):
            notifications.append(("recovery", occurred_at))
            return True

    class FailingLadderService:
        async def fetch_and_save_matches(self, _db, limit):
            raise RuntimeError("private database detail")

    class SuccessfulLadderService:
        async def fetch_and_save_matches(self, _db, limit):
            return 0

    class FakeEconomyService:
        def settle_all(self, _db):
            return None

    class FakeMarketService:
        def settle_due(self, _db):
            return 0

        def expire_open_offers(self, _db):
            return 0

    worker.alerts = FakeAlerts()
    worker._complete_due_wars = lambda: asyncio.sleep(0, result=0)
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr(scheduler_module, "BFMELadderService", FailingLadderService)
    monkeypatch.setattr(scheduler_module, "ClanEconomyService", FakeEconomyService)
    monkeypatch.setattr(scheduler_module, "ClanMarketService", FakeMarketService)

    with pytest.raises(RuntimeError):
        asyncio.run(worker.run_cycle())

    heartbeat = db.get(WorkerHeartbeat, "campaign")
    assert heartbeat.consecutive_failures == 1
    assert heartbeat.last_notification_at is not None
    assert heartbeat.replay_synced_through_at is None
    monkeypatch.setattr(scheduler_module, "BFMELadderService", SuccessfulLadderService)

    asyncio.run(worker.run_cycle())

    db.refresh(heartbeat)
    assert heartbeat.consecutive_failures == 0
    assert heartbeat.replay_synced_through_at is not None
    assert [item[0] for item in notifications] == ["failure", "recovery"]
