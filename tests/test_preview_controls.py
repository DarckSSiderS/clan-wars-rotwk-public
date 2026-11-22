from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import Response

from app.admin_preview_backend import PreviewBackendAuth, install_preview_controls


def client_with_controls():
    app = FastAPI()
    calls = []

    async def catch_all(scope, receive, send):
        await Response(status_code=404)(scope, receive, send)

    app.mount('/', catch_all)
    install_preview_controls(app, database=Path('/test/preview.db'),
        read=lambda database: {'mode': 'preparation', 'cycle_id': 2},
        switch=lambda database, mode, confirm_reset=False: calls.append((mode, confirm_reset)) or {'mode': mode, 'cycle_id': 3})
    app.add_middleware(PreviewBackendAuth, key='x' * 48, token_provider=lambda: 'only-test-session')
    return TestClient(app), calls


def test_controls_are_before_static_mount_but_require_private_gateway_key():
    client, _ = client_with_controls()
    path = '/api/v1/admin-preview/scenario'
    assert client.get(path).status_code == 404
    response = client.get(path, headers={'x-clanwar-preview-key': 'x' * 48})
    assert response.status_code == 200
    assert response.json() == {'mode': 'preparation', 'cycle_id': 2}


def test_switch_has_strict_modes_and_passes_confirmation_without_accepting_paths():
    client, calls = client_with_controls()
    path = '/api/v1/admin-preview/scenario'
    headers = {'x-clanwar-preview-key': 'x' * 48}
    assert client.post(path, headers=headers, json={'mode': 'production'}).status_code == 422
    assert client.post(path, headers=headers, json={'mode': 'battle', 'database': '/working.db'}).status_code == 422
    assert not calls
    response = client.post(path, headers=headers, json={'mode': 'battle', 'confirm_reset': False})
    assert response.status_code == 200
    assert calls == [('battle', False)]


def test_controls_are_not_installed_in_normal_application():
    from app.main import app
    assert not any(getattr(route, 'path', '') == '/api/v1/admin-preview/scenario' for route in app.routes)
