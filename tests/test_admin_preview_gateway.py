import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.requests import Request
from starlette.testclient import TestClient

from app.admin_preview_gateway import AdminPreviewGateway


ORIGIN = "https://bfmecw.online"
PREFIX = "/admin/preview"


def make_client(tmp_path, *, admin=True, upstream=None):
    config = tmp_path / "gateway.json"
    config.write_text(json.dumps({
        "key": "private-preview-key-not-for-browser",
        "public_origin": ORIGIN,
    }), encoding="utf-8")
    calls = []

    async def handler(request):
        calls.append(request)
        if upstream:
            return upstream(request)
        return httpx.Response(200, json={"path": request.url.path})

    app = FastAPI()

    @app.get("/{path:path}")
    def regular(path):
        return HTMLResponse('<html><body><div id="root">current</div></body></html>')

    app.add_middleware(
        AdminPreviewGateway, config_path=config,
        admin_check=lambda scope: admin,
        transport=httpx.MockTransport(handler),
    )
    return TestClient(app, base_url=ORIGIN), calls, config


@pytest.mark.parametrize("path", ["/", "/api/v1/admin/overview", "/assets/app.js"])
def test_preview_paths_are_not_available_to_non_admins(tmp_path, path):
    client, calls, _ = make_client(tmp_path, admin=False)
    response = client.get(PREFIX + path)
    assert response.status_code == 404
    assert not calls
    assert response.headers["cache-control"] == "no-store"


def test_admin_proxy_isolated_request_and_response_cookies(tmp_path):
    def upstream(request):
        assert request.headers["x-clanwar-preview-key"] == "private-preview-key-not-for-browser"
        assert "cookie" not in request.headers
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"ok": True}, headers={
            "set-cookie": "rotwk_session=bad; Path=/",
            "cache-control": "public, max-age=99999",
        })

    client, calls, _ = make_client(tmp_path, upstream=upstream)
    response = client.post(PREFIX + "/api/v1/test?x=2", json={"demo": 1}, headers={
        "origin": ORIGIN, "cookie": "rotwk_session=production-secret",
        "authorization": "Bearer forbidden", "x-clanwar-preview-key": "forged",
    })
    assert response.status_code == 200
    assert calls[0].url.host == "127.0.0.1"
    assert calls[0].url.path == "/api/v1/test"
    assert calls[0].url.query == b"x=2"
    assert json.loads(calls[0].content) == {"demo": 1}
    assert "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
    assert f"connect-src {ORIGIN}{PREFIX}/" in response.headers["content-security-policy"]
    connect = next(part.strip() for part in response.headers['content-security-policy'].split(';') if part.strip().startswith('connect-src '))
    assert connect.split() == ['connect-src', f'{ORIGIN}{PREFIX}/', 'blob:']


@pytest.mark.parametrize("origin", [None, "https://evil.example", "null"])
def test_preview_mutations_require_same_origin(tmp_path, origin):
    client, calls, _ = make_client(tmp_path)
    headers = {"origin": origin} if origin else {}
    assert client.post(PREFIX + "/api/v1/clans", headers=headers).status_code == 403
    assert not calls


def test_missing_config_disables_preview_without_changing_regular_pages(tmp_path):
    client, calls, config = make_client(tmp_path)
    config.unlink()
    assert client.get(PREFIX + "/").status_code == 503
    assert client.get("/").text == '<html><body><div id="root">current</div></body></html>'
    assert not calls


def test_preview_root_redirect_and_admin_launcher(tmp_path):
    client, _, _ = make_client(tmp_path)
    response = client.get(PREFIX, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == PREFIX + "/"
    response = client.get("/admin")
    assert 'href="/admin/preview/"' in response.text
    assert response.headers["cache-control"] == "no-store"
    assert PREFIX not in client.get("/").text


def test_non_admin_admin_document_is_unchanged(tmp_path):
    client, _, _ = make_client(tmp_path, admin=False)
    response = client.get("/admin")
    assert response.text == '<html><body><div id="root">current</div></body></html>'


def test_admin_launcher_works_with_real_static_document_and_outer_middleware(tmp_path):
    from app.main import SPAStaticFiles

    _, _, config = make_client(tmp_path)
    (tmp_path / 'index.html').write_text('<html><body><div id="root"></div></body></html>', encoding='utf-8')
    app = FastAPI()

    @app.middleware('http')
    async def context(request, call_next):
        return await call_next(request)

    app.add_middleware(AdminPreviewGateway, config_path=config, admin_check=lambda scope: True)
    app.mount('/', SPAStaticFiles(directory=str(tmp_path), html=True))

    @app.middleware('http')
    async def cache(request, call_next):
        return await call_next(request)

    response = TestClient(app).get('/admin')
    assert 'href="/admin/preview/"' in response.text


@pytest.mark.parametrize("location", ["/clans", "http://127.0.0.1:8182/clans"])
def test_redirects_cannot_leave_preview(tmp_path, location):
    client, _, _ = make_client(tmp_path, upstream=lambda _: httpx.Response(307, headers={"location": location}))
    response = client.get(PREFIX + "/clans/", follow_redirects=False)
    assert response.headers["location"] == PREFIX + "/clans"


def test_external_redirect_is_blocked(tmp_path):
    client, _, _ = make_client(tmp_path, upstream=lambda _: httpx.Response(302, headers={"location": "https://evil.example"}))
    assert client.get(PREFIX + "/", follow_redirects=False).status_code == 502


@pytest.mark.parametrize('location', ['../api/v1/users/me', '/../../api/v1/users/me', '/%2e%2e/%2e%2e/api/v1/users/me', '/foo\\..\\..\\api/v1/users/me'])
def test_redirect_traversal_cannot_reach_main_site(tmp_path, location):
    client, _, _ = make_client(tmp_path, upstream=lambda _: httpx.Response(302, headers={'location': location}))
    assert client.get(PREFIX + '/', follow_redirects=False).status_code == 502


def test_preview_auth_mutations_cannot_revoke_shared_test_session(tmp_path):
    client, calls, _ = make_client(tmp_path)
    response = client.post(PREFIX + "/api/v1/auth/logout", headers={"origin": ORIGIN})
    assert response.status_code == 403
    assert not calls


def test_upstream_failure_is_local_to_preview(tmp_path):
    def unavailable(request):
        raise httpx.ConnectError("offline", request=request)

    client, _, _ = make_client(tmp_path, upstream=unavailable)
    assert client.get(PREFIX + "/").status_code == 503
    assert client.get("/").status_code == 200


@pytest.mark.parametrize("role,active,revoked,impersonation,expected", [
    ("admin", True, False, False, True),
    ("user", True, False, False, False),
    ("admin", False, False, False, False),
    ("admin", True, True, False, False),
    ("admin", True, False, True, False),
])
def test_real_session_policy(db, monkeypatch, role, active, revoked, impersonation, expected):
    from datetime import datetime, timezone
    from contextlib import nullcontext
    from app import database
    from app.admin_preview_gateway import is_admin_session
    from app.config import settings
    from app.models.auth_session import UserSession
    from app.models.role import Role
    from app.models.user import User
    from app.services.session_service import SessionService

    admin_role = Role(name="admin")
    user_role = Role(name="user")
    db.add_all([admin_role, user_role])
    db.flush()
    actor = User(username="real-admin", role=admin_role, is_active=True)
    target = User(username="preview-viewer", role=admin_role if role == "admin" else user_role, is_active=active)
    db.add_all([actor, target])
    db.commit()
    issue = SessionService().issue(db, target, impersonated_by_user_id=actor.id if impersonation else None)
    if revoked:
        db.query(UserSession).filter_by(user_id=target.id).update({"revoked_at": datetime.now(timezone.utc)})
        db.commit()
    monkeypatch.setattr(database, "SessionLocal", lambda: nullcontext(db))
    scope = {"type": "http", "headers": [(b"cookie", f"{settings.SESSION_COOKIE_NAME}={issue.token}".encode())]}
    assert is_admin_session(scope) is expected


def test_private_backend_requires_shared_key_and_uses_own_cookie():
    from app.admin_preview_backend import PreviewBackendAuth

    app = FastAPI()

    @app.get("/api/v1/auth/session")
    def session(request: Request):
        return {"cookie": request.headers.get("cookie"), "key": request.headers.get("x-clanwar-preview-key")}

    app.add_middleware(PreviewBackendAuth, key="x" * 48, token_provider=lambda: "test-only-token")
    client = TestClient(app)
    assert client.get("/api/v1/auth/session").status_code == 404
    response = client.get("/api/v1/auth/session", headers={
        "x-clanwar-preview-key": "x" * 48, "cookie": "rotwk_session=production-secret",
    })
    assert response.json() == {"cookie": "clanwar_preview_session=test-only-token", "key": None}
