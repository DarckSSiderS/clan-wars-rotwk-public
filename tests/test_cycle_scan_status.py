import asyncio
from contextlib import nullcontext
from datetime import timedelta

import pytest

from app.core.time import as_utc, utc_now
from app.models.cycle_arena_scan import CycleArenaScanState
from app.services.arena_replay_scan import ArenaReplayScan
from app.services.cycle_administration_service import CycleAdministrationService
import app.services.scheduler_service as scheduler


@pytest.mark.parametrize('complete', [False, True])
def test_worker_records_only_a_completed_source_scan(db, monkeypatch, complete):
    now = utc_now()
    scan = ArenaReplayScan(now - timedelta(days=1), now, 'trusted:scan', frozenset({'1', '2'}))
    class Runtime:
        def tick(self, db, **kwargs):
            return True
    class Ladder:
        last_completed_scan = scan if complete else None
        async def fetch_and_save_matches(self, db, limit):
            return 0
    class Intake:
        def ingest_pending(self, db, **kwargs):
            return dict(source_errors=0, pending_receipts=0)
        def verify_pending(self, db, **kwargs):
            return {}
    class Backfill:
        async def process_pending(self, db):
            return 0
    monkeypatch.setattr(scheduler, 'SessionLocal', lambda: nullcontext(db))
    monkeypatch.setattr(scheduler, 'CycleRuntimeService', Runtime)
    monkeypatch.setattr(scheduler, 'BFMELadderService', Ladder)
    monkeypatch.setattr(scheduler, 'CycleArenaIngestionService', Intake)
    monkeypatch.setattr(scheduler, 'ArenaMatchBackfillService', Backfill)
    asyncio.run(scheduler.CampaignWorker().run_cycle())
    row = db.get(CycleArenaScanState, 'bfmeladder')
    assert (row is not None) is complete
    if complete:
        assert as_utc(row.covered_end) == now and row.replays_count == 2


def test_scan_status_survives_restart_and_cannot_regress_or_use_heartbeat(db):
    now = utc_now()
    service = CycleAdministrationService()
    scan = ArenaReplayScan(now - timedelta(days=1), now, 'saved', frozenset({'one'}))
    service.record_complete_scan(db, scan=scan, now=now)
    db.commit()
    db.expire_all()
    older = ArenaReplayScan(now - timedelta(days=2), now - timedelta(hours=1), 'older')
    service.record_complete_scan(db, scan=older, now=now)
    assert as_utc(db.get(CycleArenaScanState, 'bfmeladder').covered_end) == now
    with pytest.raises(ValueError):
        service.record_complete_scan(db, scan=dict(heartbeat_at=now), now=now)
    with pytest.raises(ValueError):
        service.record_complete_scan(db, scan=scan, now=now - timedelta(minutes=1))
