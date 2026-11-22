import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.main import app
from app.api.v1.achievements import router as achievement_router
from app.api.v1.localization import router as localization_router
from app.api.v1.territories import router as territory_router
from app.api.v1.users import router as user_router
from app.api.v1.wars import router as war_router
from app.api.v1.admin import router as admin_router
from app.api.v1.admin_clan_warfare import router as admin_clan_warfare_router
from app.api.v1.scheduler import router as scheduler_router
from app.config import settings
from app.core.auth import (
    authenticate_user,
    get_current_active_user,
    get_current_admin_user,
    get_current_session,
    get_current_user,
    get_onboarded_active_user,
)
from app.core.security import create_access_token, get_password_hash
from app.models.role import Role
from app.models.user import User
from app.services.session_service import SessionService


def find_route(router, path, method):
    return next(
        route
        for route in router.routes
        if isinstance(route, APIRoute) and route.path == path and method in route.methods
    )


def dependency_calls(route):
    return {dependency.call for dependency in route.dependant.dependencies}


def assert_admin_only(router, path, method):
    route = find_route(router, path, method)
    assert get_current_admin_user in dependency_calls(route)


def test_unsafe_mutations_are_admin_only():
    assert_admin_only(user_router, "/users/{user_id:int}/balance", "PUT")
    assert_admin_only(territory_router, "/{territory_id:int}", "PUT")
    assert_admin_only(territory_router, "/{territory_id:int}", "DELETE")
    assert_admin_only(war_router, "/wars/{war_id:int}/end", "PUT")
    assert_admin_only(localization_router, "/", "POST")
    assert_admin_only(achievement_router, "/achievements/", "POST")
    assert_admin_only(scheduler_router, "/scheduler/status", "GET")
    assert_admin_only(
        user_router,
        "/users/{user_id:int}/external-identity/verification",
        "PUT",
    )
    assert_admin_only(
        user_router,
        "/users/external-identities/pending",
        "GET",
    )
    assert_admin_only(admin_router, "/admin/users", "GET")
    assert_admin_only(admin_router, "/admin/users/{user_id:int}/role", "PATCH")
    assert_admin_only(admin_router, "/admin/titles", "POST")
    assert_admin_only(admin_router, "/admin/titles/{title_id:int}", "PATCH")
    assert_admin_only(admin_router, "/admin/titles/{title_id:int}/users/{user_id:int}", "POST")
    assert_admin_only(admin_router, "/admin/titles/{title_id:int}/users/{user_id:int}", "DELETE")
    assert_admin_only(
        admin_clan_warfare_router,
        "/admin/clan-warfare/wars/{war_id:int}",
        "GET",
    )


def test_unknown_api_responses_disable_browser_caching():
    response = TestClient(app).get("/api/cache-header-probe")

    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-cache, no-store, must-revalidate"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"


def test_http_responses_include_a_traceable_request_id():
    client = TestClient(app)

    generated = client.get("/api/request-id-probe")
    supplied = client.get(
        "/api/request-id-probe",
        headers={"X-Request-ID": "support-ticket-42"},
    )
    unsafe = client.get(
        "/api/request-id-probe",
        headers={"X-Request-ID": "invalid request id"},
    )

    assert len(generated.headers["x-request-id"]) == 32
    assert supplied.headers["x-request-id"] == "support-ticket-42"
    assert unsafe.headers["x-request-id"] != "invalid request id"


def _request(*, cookie=None, authorization=None):
    headers = []
    if cookie is not None:
        headers.append(
            (b"cookie", f"{settings.SESSION_COOKIE_NAME}={cookie}".encode("ascii"))
        )
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("ascii")))
    return Request({"type": "http", "headers": headers})


def _create_user(db, username="player", role_name="user", **values):
    role = db.query(Role).filter(Role.name == role_name).first()
    if role is None:
        role = Role(name=role_name, description=role_name)
        db.add(role)
        db.flush()
    user = User(
        username=username,
        email=f"{username}@example.test",
        hashed_password=values.pop("hashed_password", "unused"),
        role=role,
        **values,
    )
    db.add(user)
    db.commit()
    return user


def test_current_user_rejects_missing_session_cookie(db):
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_current_session(request=_request(), db=db))

    assert exc_info.value.status_code == 401
    assert "WWW-Authenticate" not in exc_info.value.headers


def test_current_user_does_not_accept_authorization_bearer(db):
    user = _create_user(db)
    bearer = create_access_token({"sub": user.username})

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            get_current_session(
                request=_request(authorization=f"Bearer {bearer}"),
                db=db,
            )
        )

    assert exc_info.value.status_code == 401


def test_current_user_resolves_only_configured_session_cookie(db):
    user = _create_user(db)
    issue = SessionService().issue(
        db,
        user,
        now=datetime.now(timezone.utc),
    )

    session = asyncio.run(
        get_current_session(request=_request(cookie=issue.token), db=db)
    )
    resolved = asyncio.run(get_current_user(session))

    assert resolved.id == user.id
    assert resolved.role.name == "user"


def test_active_user_rejects_inactive_user_without_admin_impersonation(db):
    user = _create_user(db, is_active=False)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_current_active_user(user))

    assert exc_info.value.status_code == 400


def test_onboarded_user_dependency_returns_machine_readable_403(db):
    user = _create_user(db, onboarding_completed_at=None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_onboarded_active_user(user))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "onboarding_required"


def test_onboarded_user_dependency_accepts_completed_user(db):
    user = _create_user(
        db,
        onboarding_completed_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )

    assert asyncio.run(get_onboarded_active_user(user)) is user


def test_admin_dependency_does_not_grant_actor_role_to_effective_user(db):
    target = _create_user(db)
    target._is_admin_impersonation = True
    target._impersonated_by_username = "administrator"

    with pytest.raises(HTTPException) as exc_info:
        get_current_admin_user(target)

    assert exc_info.value.status_code == 403


def test_admin_dependency_rejects_regular_user(db):
    user = _create_user(db)

    with pytest.raises(HTTPException) as exc_info:
        get_current_admin_user(user)

    assert exc_info.value.status_code == 403


def test_password_authentication_does_not_map_master_admin_alias(db):
    password = "correct horse battery staple"
    _create_user(
        db,
        username="darcks",
        role_name="admin",
        hashed_password=get_password_hash(password),
    )

    assert authenticate_user(db, "admin", password) is None
