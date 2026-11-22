import importlib
import importlib.util
from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.database import get_db
from app.models.role import Role
from tests.test_cycle_interception_review_service import resolved, reviewer
from tests.test_cycle_operations_api import no_network
from tests.test_cycle_reinforcement_store import world, T


def client_for(db, world, monkeypatch):
    name = 'app.api.v1.cycle_interception_review'
    assert importlib.util.find_spec(name), 'Нет отдельного API пересмотра'
    api = importlib.import_module(name)
    reviewer(monkeypatch)
    resolved(db, world)
    role = Role(name='admin')
    db.add(role)
    world[0][7].role = role
    db.commit()
    app = FastAPI()
    app.include_router(api.router, prefix='/api/v1/campaign/cycles')
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: world[0][7]
    return TestClient(app), app, f'/api/v1/campaign/cycles/{world[3].id}/interception/review'


def test_review_http_is_admin_only_and_requires_strict_command(db, world, monkeypatch):
    client, app, url = client_for(db, world, monkeypatch)
    data = client.get(url, params={'dispatch_id': 'd'})
    assert data.status_code == 200
    assert data.json()['audit'] == []
    command = dict(command_id='http-review', reason='Ошибка зачёта', expected_revision=data.json()['revision'],
        replay_id='bfmeladder:interception-game', user_id=world[0][1].id, counted=False)
    response = client.post(url + '/contributions?dispatch_id=d', json=command)
    assert response.status_code == 200, response.text
    assert client.post(url + '/contributions?dispatch_id=d', json=command).json() == response.json()
    read = client.get(url, params={'dispatch_id': 'd'}).json()
    assert len(read['audit']) == 1
    for bad in ({'reason': ' '}, {'expected_revision': True}, {'counted': 'false'}, {'command_id': ''}, {'now': '2099-01-01'}):
        assert client.post(url + '/contributions?dispatch_id=d', json={**command, **bad}).status_code == 409
    app.dependency_overrides[get_current_active_user] = lambda: world[0][0]
    assert client.get(url, params={'dispatch_id': 'd'}).status_code == 403
    assert client.post(url + '/contributions?dispatch_id=d', json=command).status_code == 403
    app.dependency_overrides.pop(get_current_active_user)
    assert client.get(url, params={'dispatch_id': 'd'}).status_code == 401


def test_outcome_http_requires_preview_and_actual_server_clock(db, world, monkeypatch):
    client, app, url = client_for(db, world, monkeypatch)
    revision = client.get(url, params={'dispatch_id': 'd'}).json()['revision']
    body = dict(command_id='adjust', reason='Ручная поправка', expected_revision=revision,
        side_clan_id=world[1][2].id, amount='1000')
    response = client.post(url + '/adjustments?dispatch_id=d', json=body)
    assert response.status_code == 200, response.text
    command = dict(command_id='preview', reason='Проверка исхода', expected_revision=response.json()['revision'])
    preview = client.post(url + '/outcome/preview?dispatch_id=d', json=command)
    assert preview.status_code == 200, preview.text
    assert preview.json()['proposed_result']['outcome'] == 'blocked'
    reviewer(monkeypatch, T + timedelta(hours=24))
    confirm = client.post(url + '/outcome/confirm?dispatch_id=d', json={**command,
        'command_id': 'confirm', 'preview_command_id': 'preview'})
    assert confirm.status_code == 409
    assert 'прибытия' in confirm.json()['detail']
