"""Real PostgreSQL interleavings; never connects without TEST_POSTGRES_URL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from queue import Queue
import time

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app.models.campaign_cycle import CampaignCycleRecord
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict
from app.services.cycle_income_service import CycleIncomeService
from app.services.cycle_ownership_service import CycleOwnershipService
from tests.test_cycle_ownership_correction import correction_world


def wait_for_block(engine, pid):
    until = time.monotonic() + 5
    with engine.connect() as connection:
        while time.monotonic() < until:
            if connection.execute(text('SELECT pg_blocking_pids(:pid)'), {'pid': pid}).scalar_one():
                return
            time.sleep(0.02)
    raise AssertionError('The correction did not reach the expected PostgreSQL lock wait')


def correction_job(factory, identifiers, ready):
    with factory() as session:
        ready.put(session.execute(text('SELECT pg_backend_pid()')).scalar_one())
        result = CycleOwnershipService().correct_ownership(session, **identifiers)
        result_id = result.id
        session.commit()
        return result_id


def inputs(db):
    users, clan, _, _, cycle, battle, now = correction_world(db)
    CampaignCycleStore().settle(db, cycle_id=cycle.id, completed_at=now)
    preview = CycleOwnershipService().preview_correction(db, battle_id=battle.id)
    args = dict(battle_id=battle.id, new_owner_clan_id=clan.id,
        preview_token=preview['preview_token'], command_id='pg-correction', actor_user_id=users[0].id,
        reason='Concurrent correction', now=now + timedelta(hours=13))
    db.commit()
    return cycle.id, cycle.rule_version, now, args


def test_postgres_worker_and_correction_acquire_latest_cycle_before_older_cycles(postgres_db):
    cycle_id, version, now, args = inputs(postgres_db)
    following = CampaignCycleStore().advance(postgres_db, cycle_id=cycle_id,
        now=now + timedelta(hours=12), rule_version=version)
    args['preview_token'] = CycleOwnershipService().preview_correction(postgres_db, battle_id=args['battle_id'])['preview_token']
    following_id = following.id
    postgres_db.commit()
    factory = sessionmaker(bind=postgres_db.bind)
    ready = Queue()
    with factory() as worker, ThreadPoolExecutor(max_workers=1) as pool:
        worker.execute(select(CampaignCycleRecord).where(CampaignCycleRecord.id == following_id).with_for_update()).scalar_one()
        future = pool.submit(correction_job, factory, args, ready)
        try:
            wait_for_block(postgres_db.bind, ready.get(timeout=5))
            assert [row.id for row in CycleIncomeService._cycles(worker, following.season_id)] == [cycle_id, following_id]
        finally:
            worker.commit()
        assert future.result(timeout=10) > 0


def test_postgres_advance_while_correction_waits_rejects_old_preview(postgres_db):
    cycle_id, version, now, args = inputs(postgres_db)
    factory = sessionmaker(bind=postgres_db.bind)
    ready = Queue()
    with factory() as worker, ThreadPoolExecutor(max_workers=1) as pool:
        worker.execute(select(CampaignCycleRecord).where(CampaignCycleRecord.id == cycle_id).with_for_update()).scalar_one()
        future = pool.submit(correction_job, factory, args, ready)
        try:
            wait_for_block(postgres_db.bind, ready.get(timeout=5))
            CampaignCycleStore().advance(worker, cycle_id=cycle_id,
                now=now + timedelta(hours=12), rule_version=version)
        finally:
            worker.commit()
        with pytest.raises(CycleConflict, match='preview'):
            future.result(timeout=10)
