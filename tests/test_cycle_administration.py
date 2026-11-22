"""Восстановление после сбоя не выдумывает исторические составы и матчи."""

from datetime import timedelta
import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_admin_user
from app.core.time import as_utc
from app.database import get_db
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.operation import AdminAuditLog
from app.models.worker import WorkerHeartbeat
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict
from app.services.campaign_pause_service import CampaignPauseService
from app.services.cycle_plan_service import CyclePlanService
from tests.test_cycle_plan_service import setup_world as base_world


def setup_world(db):
    from app.services.cycle_startup_service import CycleStartupService
    world = base_world(db)
    CycleStartupService().initialize(db, cycle_id=world[3].id, now=as_utc(world[3].starts_at))
    return world


def service():
    try:
        return importlib.import_module('app.services.cycle_administration_service').CycleAdministrationService()
    except ModuleNotFoundError:
        pytest.fail('Не реализована явная административная процедура восстановления цикла')


def recover(db, user, cycle, now, **overrides):
    kwargs = dict(cycle_id=cycle.id, actor_user_id=user.id, expected_revision=cycle.revision,
        command_id='restore-1', reason='Сервер пропустил подготовку', now=now)
    kwargs.update(overrides)
    return service().recover_preparation(db, **kwargs)


def test_recovery_gives_real_24_hour_preparation_without_resetting_season(db):
    users, clan, land, cycle = setup_world(db)
    before_start = cycle.starts_at
    now = CampaignCycleStore.timeline(cycle).replay_deadline + timedelta(days=2)
    result = recover(db, users[0], cycle, now)
    assert as_utc(cycle.preparation_at) == now
    assert CampaignCycleStore.timeline(cycle).battle_at == now + timedelta(hours=24)
    assert cycle.planning_snapshot is not None and cycle.orders_frozen_at is None
    assert cycle.starts_at == before_start
    assert result['cycle_id'] == cycle.id and result['revision'] == cycle.revision
    assert db.query(CampaignCycleRecord).count() == 1
    assert db.get(type(clan), clan.id).is_deleted is False
    assert db.query(AdminAuditLog).filter_by(action='cycle_preparation_recovered').count() == 1


def test_recovery_retry_is_durable_and_conflicting_command_is_rejected(db):
    users, _, _, cycle = setup_world(db)
    now = CampaignCycleStore.timeline(cycle).battle_at + timedelta(days=1)
    revision = cycle.revision
    first = recover(db, users[0], cycle, now)
    db.commit()
    again = recover(db, users[0], cycle, now + timedelta(hours=1), expected_revision=revision)
    assert first == again
    assert as_utc(cycle.preparation_at) == now
    with pytest.raises(ValueError):
        recover(db, users[0], cycle, now, reason='Другая причина')


def test_recovery_cannot_overwrite_existing_snapshot_or_future_preparation(db):
    users, _, _, cycle = setup_world(db)
    timeline = CampaignCycleStore.timeline(cycle)
    with pytest.raises(ValueError):
        recover(db, users[0], cycle, timeline.preparation_at)
    CyclePlanService().capture_preparation(db, cycle_id=cycle.id, now=timeline.preparation_at)
    with pytest.raises(ValueError):
        recover(db, users[0], cycle, timeline.battle_at + timedelta(days=1))
    assert cycle.orders_frozen_at is None


def test_recovery_revision_conflict_and_capture_failure_are_atomic(db, monkeypatch):
    users, _, _, cycle = setup_world(db)
    old = as_utc(cycle.preparation_at)
    now = CampaignCycleStore.timeline(cycle).battle_at
    with pytest.raises(CycleConflict):
        recover(db, users[0], cycle, now, expected_revision=cycle.revision + 1)
    def broken(*args, **kwargs):
        raise ValueError('Не удалось сохранить снимок')
    monkeypatch.setattr(CyclePlanService, 'capture_preparation', broken)
    with pytest.raises(ValueError):
        recover(db, users[0], cycle, now)
    assert as_utc(cycle.preparation_at) == old
    assert db.query(AdminAuditLog).count() == 0


def test_legacy_pause_explicitly_rejects_new_cycle_mode(db):
    users, _, _, _ = setup_world(db)
    with pytest.raises(ValueError, match='цикл'):
        CampaignPauseService().pause(db, actor_user_id=users[0].id, reason='Проверка')
    assert not CampaignPauseService.is_paused(db)


def test_diagnostics_never_confuses_worker_heartbeat_with_complete_scan(db):
    _, _, _, cycle = setup_world(db)
    now = CampaignCycleStore.timeline(cycle).battle_at
    db.add(WorkerHeartbeat(worker_name='campaign', heartbeat_at=now,
        last_success_at=now, replay_synced_through_at=now, consecutive_failures=0))
    db.flush()
    result = service().diagnostics(db, now=now)
    assert result['cycle']['recovery_available'] is True
    assert result['arena']['last_complete_scan'] is None
    assert result['arena']['heartbeat_at'] == now
    assert 'planning_snapshot' not in str(result) and 'command_id' not in str(result)


def test_administration_endpoints_are_admin_only(db, monkeypatch):
    users, _, _, cycle = setup_world(db)
    service()
    api = importlib.import_module('app.api.v1.cycle_administration')
    app = FastAPI()
    app.include_router(api.router, prefix='/cycles')
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    assert client.get('/cycles/admin/diagnostics').status_code in (401, 403)
    app.dependency_overrides[get_current_admin_user] = lambda: users[0]
    now = CampaignCycleStore.timeline(cycle).battle_at
    monkeypatch.setattr(api, 'utc_now', lambda: now)
    assert client.get('/cycles/admin/diagnostics').json()['cycle']['recovery_available']
    response = client.post(f'/cycles/admin/cycles/{cycle.id}/recover-preparation', json={
        'expected_revision': cycle.revision, 'command_id': 'http-1', 'reason': 'Восстановление после сбоя'})
    assert response.status_code == 200


def test_unsupported_pause_api_returns_clear_conflict_not_server_error(db):
    from app.api.v1.scheduler import router
    users, _, _, _ = setup_world(db)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_admin_user] = lambda: users[0]
    response = TestClient(app, raise_server_exceptions=False).post('/scheduler/campaign/pause',
        json={'reason': 'Проверка недоступной паузы'})
    assert response.status_code == 409
    assert 'цикл' in response.json()['detail']


def test_admin_ui_uses_the_real_campaign_router_prefix():
    from pathlib import Path
    source = (Path(__file__).parents[1] / 'frontend/src/pages/AdminDashboardPage.jsx').read_text(encoding='utf-8')
    assert "api.get('/campaign/cycles/admin/diagnostics')" in source
    assert 'api.post(`/campaign/cycles/admin/cycles/${cycle.id}/recover-preparation`' in source
