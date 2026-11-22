from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient

from app.database import Base
from app.main import app


def test_petitions_have_no_registered_routes_or_models():
    assert not any('/petitions' in route.path for route in iter_route_contexts(app.routes))
    assert not any(name == 'petitions' or name.startswith('petition_') for name in Base.metadata.tables)


def test_old_petition_urls_are_not_found():
    with TestClient(app) as client:
        for method, path in [('GET', '/petitions'), ('POST', '/petitions'), ('GET', '/petitions/1'),
            ('POST', '/petitions/1/vote'), ('GET', '/petitions/1/comments'),
            ('POST', '/petitions/1/comments'), ('PATCH', '/petitions/1/status'),
            ('PUT', '/petitions/1/comments/1/reaction'), ('DELETE', '/petitions/1/comments/1')]:
            assert client.request(method, '/api/v1' + path).status_code == 404
