"""Проверяет явные решения по поздним играм без пересчёта владений."""

from datetime import timedelta

import pytest
from sqlalchemy import event

from app.models.cycle_battle import CycleMatchContribution
from app.core.time import as_utc
from tests.test_cycle_arena_ingestion import saved
from tests.test_cycle_late_replays import finished
from tests.test_cycle_campaign_api import client_for


def service():
    from app.services.cycle_late_replay_review_service import CycleLateReplayReviewService
    return CycleLateReplayReviewService()


def setup(db, monkeypatch, *, ratings=True):
    users, home, away, cycle, battle, replay = finished(db)
    match = saved(db, replay)
    if ratings:
        monkeypatch.setattr('app.services.cycle_arena_ingestion_service.CycleArenaIngestionService.adapt',
                            staticmethod(lambda _match: replay))
    return users, home, away, cycle, battle, match


def test_preview_has_real_formula_without_writes_or_private_identity(db, monkeypatch):
    _, _, _, cycle, battle, match = setup(db, monkeypatch)
    statements = []
    listener = lambda _c, _s, sql, *_args: statements.append(sql)
    event.listen(db.bind, 'before_cursor_execute', listener)
    try:
        result = service().preview(db, battle_id=battle.id, match_id=match.id)
    finally:
        event.remove(db.bind, 'before_cursor_execute', listener)
    assert result['can_accept'] and len(result['players']) == 2
    assert result['preview_token'] and all(row['reason'] == 'counted' for row in result['players'])
    assert 'uuid' not in str(result) and 'input_fingerprint' not in str(result)
    assert not any(sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for sql in statements)
    assert db.query(CycleMatchContribution).count() == 0


@pytest.mark.parametrize('database', ['db', 'postgres_db'])
def test_accept_is_audited_and_retry_does_not_duplicate_or_change_owner(request, database, monkeypatch):
    db = request.getfixturevalue(database)
    users, home, _, cycle, battle, match = setup(db, monkeypatch)
    svc = service()
    before = battle.winner_clan_id, as_utc(battle.ownership_applied_at), as_utc(cycle.import_verified_at), as_utc(cycle.settled_at)
    preview = svc.preview(db, battle_id=battle.id, match_id=match.id)
    args = dict(battle_id=battle.id, match_id=match.id, preview_token=preview['preview_token'],
                counted=True, command_id='late-accept', actor_user_id=users[0].id,
                reason='Игра пропущена при недоступности сайта', now=battle.completed_at + timedelta(days=1))
    decision = svc.decide(db, **args)
    assert svc.decide(db, **args).id == decision.id
    rows = db.query(CycleMatchContribution).all()
    assert len(rows) == 2 and all(row.counted and row.reviewed_by_user_id == users[0].id for row in rows)
    assert all(row.review_reason == args['reason'] for row in rows)
    assert decision.user_ids == sorted(row.user_id for row in rows)
    assert decision.counted is True
    assert before == (battle.winner_clan_id, as_utc(battle.ownership_applied_at),
                      as_utc(cycle.import_verified_at), as_utc(cycle.settled_at))
    assert battle.recalculated_winner_clan_id in {side['clan_id'] for side in battle.sides} | {None}
    with pytest.raises(ValueError):
        svc.decide(db, **{**args, 'counted': False})


def test_reject_without_historical_elo_is_allowed_but_accept_is_not(db, monkeypatch):
    users, _, _, _, battle, match = setup(db, monkeypatch, ratings=False)
    svc = service()
    preview = svc.preview(db, battle_id=battle.id, match_id=match.id)
    assert not preview['can_accept']
    args = dict(battle_id=battle.id, match_id=match.id, preview_token=preview['preview_token'],
                command_id='late-decision', actor_user_id=users[0].id,
                reason='Решение после проверки', now=battle.completed_at + timedelta(days=1))
    with pytest.raises(ValueError):
        svc.decide(db, counted=True, **args)
    assert db.query(CycleMatchContribution).count() == 0
    svc.decide(db, counted=False, **args)
    rows = db.query(CycleMatchContribution).all()
    assert len(rows) == 2 and all(not row.counted and row.points == 0 for row in rows)
    from app.services.cycle_late_replay_service import CycleLateReplayService
    assert CycleLateReplayService().read(db, battle_id=battle.id)['items'] == []


@pytest.mark.parametrize('change', ['source', 'cycle', 'contribution'])
def test_changed_preview_requires_a_new_confirmation(db, monkeypatch, change):
    users, _, _, cycle, battle, match = setup(db, monkeypatch)
    svc = service()
    preview = svc.preview(db, battle_id=battle.id, match_id=match.id)
    if change == 'source':
        match.source_payload = {**match.source_payload, 'changed': True}
    elif change == 'cycle':
        cycle.revision += 1
    else:
        db.add(CycleMatchContribution(battle_id=battle.id, replay_id='bfmeladder:arena-1',
            user_id=users[2].id, clan_id=battle.sides[0]['clan_id'], counted=False, points=0,
            reason='admin_rejected', review_reason='Ранее проверено', reviewed_by_user_id=users[0].id))
    db.flush()
    with pytest.raises(ValueError):
        svc.decide(db, battle_id=battle.id, match_id=match.id, preview_token=preview['preview_token'],
                   counted=True, command_id='stale', actor_user_id=users[0].id,
                   reason='Устаревший просмотр', now=battle.completed_at + timedelta(days=1))


def test_admin_api_requires_preview_reason_and_hides_write_from_ordinary_user(db, monkeypatch):
    users, _, _, _, battle, match = setup(db, monkeypatch)
    now = as_utc(battle.completed_at) + timedelta(days=1)
    monkeypatch.setattr('app.api.v1.cycle_campaign.utc_now', lambda: now)
    url = f'/cycles/battles/{battle.id}/late-replays/{match.id}'
    ordinary = client_for(db, users[2])
    assert ordinary.get(url).status_code in (401, 403)
    assert ordinary.post(url, json={}).status_code in (401, 403, 422)
    admin = client_for(db, users[0], admin=True)
    preview = admin.get(url)
    assert preview.status_code == 200
    body = dict(preview_token=preview.json()['preview_token'], counted=True,
                command_id='api-late', reason='Проверено администратором')
    assert admin.post(url, json={**body, 'reason': ''}).status_code == 422
    response = admin.post(url, json=body)
    assert response.status_code == 200, response.text
    assert len(response.json()['contributions']) == 2


def test_foreign_replay_and_active_battle_are_not_reviewable(db, monkeypatch):
    _, _, _, _, battle, match = setup(db, monkeypatch)
    svc = service()
    with pytest.raises(ValueError):
        svc.preview(db, battle_id=battle.id, match_id=match.id + 100)
    battle.completed_at = None
    db.flush()
    with pytest.raises(ValueError):
        svc.preview(db, battle_id=battle.id, match_id=match.id)


def test_postgres_simultaneous_retries_share_one_decision(postgres_db, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import sessionmaker
    from app.models.cycle_battle import CycleLateReplayDecision

    db = postgres_db
    users, _, _, _, battle, match = setup(db, monkeypatch)
    preview = service().preview(db, battle_id=battle.id, match_id=match.id)
    args = dict(battle_id=battle.id, match_id=match.id, preview_token=preview['preview_token'],
        counted=True, command_id='simultaneous', actor_user_id=users[0].id,
        reason='Параллельный повтор', now=as_utc(battle.completed_at) + timedelta(days=1))
    db.commit()
    factory, barrier = sessionmaker(bind=db.bind), Barrier(2, timeout=10)

    def run():
        with factory() as session:
            barrier.wait()
            row = service().decide(session, **args)
            result = row.id
            session.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(run) for _ in range(2)]
        results = [job.result(timeout=20) for job in jobs]
    assert results[0] == results[1]
    assert db.query(CycleLateReplayDecision).count() == 1
    assert db.query(CycleMatchContribution).count() == 2
