"""Технический режим перехода не открывает БД и не принимает изменения."""
import importlib
from threading import Event

import pytest
from starlette.testclient import TestClient


def module():
    try:
        return importlib.import_module('deploy.cutover_maintenance')
    except ModuleNotFoundError:
        pytest.fail('Нет изолированного технического приложения перехода')


@pytest.mark.parametrize('method,path', [
    ('GET', '/api/v1/territories/'), ('POST', '/api/v1/wars/'),
    ('PATCH', '/api/v1/admin/clans/1/economy'), ('DELETE', '/api/v1/clans/1'),
    ('PUT', '/api/v1/users/1'), ('POST', '/__cutover__/status'),
])
def test_all_application_requests_are_blocked_without_database(method, path, monkeypatch):
    import app.database
    def forbidden(*args, **kwargs):
        raise AssertionError('Технический режим не должен открывать БД')
    monkeypatch.setattr(app.database, 'SessionLocal', forbidden)
    with TestClient(module().create_app('season-one-cutover-test')) as client:
        response = client.request(method, path,
            headers={'Authorization': 'Bearer synthetic-not-a-real-token'})
    assert response.status_code == 503
    assert response.json()['maintenance'] is True
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['retry-after'] == '60'
    assert 'synthetic-not-a-real-token' not in response.text


def test_marker_identifies_maintenance_but_readiness_remains_unavailable():
    with TestClient(module().create_app('season-one-cutover-test')) as client:
        assert client.get('/__cutover__/status').json() == {
            'maintenance': True, 'release': 'season-one-cutover-test'}
        assert client.get('/health/live').status_code == 200
        assert client.get('/health/ready').status_code == 503
        response = client.get('/')
        assert response.status_code == 503
        assert 'Техническое обновление' in response.text
        assert '<script' not in response.text
        assert "default-src 'none'" in response.headers['content-security-policy']
        assert client.get('/maintenance.css').headers['content-type'].startswith('text/css')
        assert client.head('/').content == b''


def test_worker_is_idle_and_accepts_an_already_set_stop_event():
    stopped = Event()
    stopped.set()
    assert module().idle_worker(stopped) is None


@pytest.mark.parametrize('marker', ['', '../release', '<script>', 'bad\nmarker'])
def test_invalid_release_marker_is_rejected(marker):
    with pytest.raises(ValueError):
        module().create_app(marker)
