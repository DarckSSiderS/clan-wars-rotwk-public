"""Гонки административных команд на отдельном тестовом PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.cycle_interception import CycleInterceptionAdjustment, CycleInterceptionReviewCommand
from app.services.campaign_cycle_store import CycleConflict
from tests.test_cycle_interception_review_service import resolved, reviewer, args, dispatch
from tests.test_cycle_reinforcement_store import world as make_world


@pytest.mark.parametrize('same_command', [True, False])
def test_concurrent_interception_adjustments_do_not_duplicate_or_overwrite(postgres_db, monkeypatch, same_command):
    db = postgres_db
    world = make_world.__wrapped__(db)
    resolved(db, world)
    service = reviewer(monkeypatch)
    before = dispatch(db, world)
    command = args(db, world, side_clan_id=world[1][0].id, amount='12.5')
    db.commit()
    factory, barrier = sessionmaker(bind=db.bind), Barrier(2, timeout=10)

    def run(index):
        with factory() as session:
            barrier.wait()
            current = dict(command, command_id='same' if same_command else f'different-{index}')
            try:
                result = service.adjust(session, **current)
                session.commit()
                return 'ok', result['adjustment_id']
            except CycleConflict:
                session.rollback()
                return 'conflict', None

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(run, index) for index in range(2)]
        results = [job.result(timeout=20) for job in jobs]
    if same_command:
        assert results[0] == results[1] and results[0][0] == 'ok'
    else:
        assert sorted(status for status, _ in results) == ['conflict', 'ok']
    db.expire_all()
    assert db.query(CycleInterceptionAdjustment).count() == 1
    assert db.query(CycleInterceptionReviewCommand).count() == 1
    assert dispatch(db, world) == before
