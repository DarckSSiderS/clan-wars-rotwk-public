from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from app.models.campaign import CampaignSeason, CampaignSeasonClanResult
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.season_archive import CampaignSeasonArchive
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.campaign_history_service import CampaignHistoryService
from app.services.cycle_market_service import CycleMarketService
from app.services.cycle_runtime_service import CycleRuntimeService
from tests.test_campaign_cycle_store import prepare, season


def final_cycle(db, *, request_end):
    owner = season(db)
    store = CampaignCycleStore()
    cycle = store.start(db, season_id=owner.id)
    prepare(db, cycle)
    deadline = store.timeline(cycle).replay_deadline
    store.mark_import_complete(db, cycle_id=cycle.id, verified_at=deadline)
    if request_end:
        store.request_end(db, cycle_id=cycle.id)
    db.commit()
    return owner.id, cycle.id, deadline


def test_completion_locks_cycle_before_season_and_keeps_final_phase_guard(db):
    owner_id, cycle_id, deadline = final_cycle(db, request_end=True)
    locks = []

    def record(orm_state):
        sql = str(orm_state.statement.compile(dialect=postgresql.dialect())).lower()
        if "for update" in sql:
            locks.append(sql)

    event.listen(db, "do_orm_execute", record)
    try:
        with pytest.raises(ValueError, match="Final cycle"):
            CampaignHistoryService().complete_active_season(db, completed_at=deadline)
    finally:
        event.remove(db, "do_orm_execute", record)
    assert "from campaign_cycles" in locks[0]
    assert "from campaign_seasons" in locks[1]
    assert len(locks) == 2
    assert db.get(CampaignSeason, owner_id).status == "active"
    assert db.get(CampaignCycleRecord, cycle_id).settled_at is None
    assert db.query(CampaignSeasonArchive).count() == 0


@pytest.mark.parametrize("request_end", [True, False])
def test_postgres_completion_and_final_tick_share_cycle_season_lock_order(postgres_db, request_end):
    db = postgres_db
    owner_id, cycle_id, deadline = final_cycle(db, request_end=request_end)
    db.rollback()
    factory = sessionmaker(bind=db.bind, autoflush=False)
    cycle_held, completion_waiting = Event(), Event()

    def observe(connection, cursor, statement, parameters, context, executemany):
        sql = statement.lower()
        if (context.execution_options.get("archive_completion") and
                "from campaign_cycles" in sql and "for update" in sql):
            completion_waiting.set()

    def tick():
        with factory() as session:
            CycleRuntimeService._latest(session, owner_id)
            cycle_held.set()
            assert completion_waiting.wait(10), "Completion did not reach its cycle lock"
            # These are the final tick's real store/market operations, including season locking.
            CampaignCycleStore().settle(session, cycle_id=cycle_id, completed_at=deadline)
            CycleMarketService().expire(session, cycle_id=cycle_id, now=deadline,
                                        command_id="archive-lock-order-final-tick")
            session.commit()

    def complete():
        assert cycle_held.wait(10), "Final tick did not acquire the cycle"
        with factory() as session:
            session.connection(execution_options={"archive_completion": True})
            # The locked reread must replace a cached pre-settlement cycle after waiting.
            cached = session.get(CampaignCycleRecord, cycle_id)
            assert cached.settled_at is None
            try:
                result = CampaignHistoryService().complete_active_season(
                    session, completed_at=deadline + timedelta(seconds=1))
                session.commit()
                return result.id
            except ValueError as error:
                session.rollback()
                assert "Final cycle" in str(error)
                return None

    event.listen(db.bind, "before_cursor_execute", observe)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            ticking, closing = pool.submit(tick), pool.submit(complete)
            ticking.result(timeout=30)
            completed_id = closing.result(timeout=30)
    finally:
        event.remove(db.bind, "before_cursor_execute", observe)
    db.expire_all()
    assert completed_id == (owner_id if request_end else None)
    assert db.get(CampaignSeason, owner_id).status == ("completed" if request_end else "active")
    assert db.query(CampaignSeasonArchive).count() == int(request_end)
    assert db.query(CampaignSeasonClanResult).count() == 0
    assert db.query(CampaignSeason).count() == db.query(CampaignCycleRecord).count() == 1
