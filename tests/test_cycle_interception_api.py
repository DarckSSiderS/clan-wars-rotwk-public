from datetime import timedelta

from app.core.auth import get_current_active_user
from tests.test_cycle_operations_api import client_for
from tests.test_cycle_reinforcement_store import world, T
from tests.test_cycle_interception_service import setup, process


def test_interception_http_is_authenticated_read_only(db, world, monkeypatch):
    process(db, world, setup(db, world))
    client, app = client_for(db, monkeypatch, world[0][7], T + timedelta(hours=3))
    url = f'/api/v1/campaign/cycles/{world[3].id}/interception?dispatch_id=d'
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()['phase'] == 'battle'
    assert 'source_cursor' not in response.text
    assert client.post(url, json={'verified': True}).status_code == 405
    assert client.get(url.replace('dispatch_id=d', 'dispatch_id=hidden')).status_code == 409
    app.dependency_overrides.pop(get_current_active_user)
    assert client.get(url).status_code == 401
