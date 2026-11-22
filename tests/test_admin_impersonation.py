from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.config import settings
from app.database import get_db
from app.main import app
from app.models.auth_session import SecurityAuditEvent
from app.models.operation import AdminAuditLog
from app.models.role import Role
from app.models.user import User
from app.services.session_service import InvalidSession, SessionService


NOW = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def api_client(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app, base_url="https://testserver") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _create_users(db, *, target_active=True, target_claimed=True):
    admin_role = Role(name="admin", description="Administrator")
    user_role = Role(name="user", description="User")
    admin = User(
        username="ActualOperator",
        display_name="Real Admin",
        email="operator@example.test",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
        onboarding_completed_at=NOW,
        role=admin_role,
    )
    target = User(
        username="Nurik1994",
        display_name="Nurik",
        email="nurik@example.test",
        hashed_password=None,
        is_active=target_active,
        is_claimed=target_claimed,
        onboarding_completed_at=NOW,
        role=user_role,
    )
    db.add_all([admin_role, user_role, admin, target])
    db.commit()
    return admin, target, user_role


def _authenticate(db, client, user):
    issue = SessionService().issue(db, user)
    client.cookies.set(
        settings.SESSION_COOKIE_NAME,
        issue.token,
        domain="testserver.local",
        path="/",
    )
    return issue.token


def _session_cookie(response):
    headers = response.headers.get_list("set-cookie")
    return next(
        value.lower()
        for value in headers
        if value.startswith(f"{settings.SESSION_COOKIE_NAME}=")
    )


def _current_cookie(client):
    return client.cookies.get(settings.SESSION_COOKIE_NAME)


def test_admin_rotates_into_audited_cookie_impersonation(db, api_client):
    admin, target, _ = _create_users(db)
    old_admin_token = _authenticate(db, api_client, admin)

    response = api_client.post(f"/api/v1/users/{target.id}/impersonate")

    assert response.status_code == 200
    assert "access_token" not in response.json()
    assert response.json()["id"] == target.id
    assert response.json()["is_admin_impersonation"] is True
    assert response.json()["impersonated_by_username"] == "ActualOperator"
    cookie = _session_cookie(response)
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie

    with pytest.raises(InvalidSession):
        SessionService().resolve(db, old_admin_token, touch=False)
    impersonated = SessionService().resolve(
        db,
        _current_cookie(api_client),
        touch=False,
    )
    assert impersonated.user_id == target.id
    assert impersonated.impersonated_by_user_id == admin.id
    assert impersonated.is_impersonation is True

    audit = db.query(AdminAuditLog).one()
    assert audit.actor_user_id == admin.id
    assert audit.action == "user_impersonation_started"
    assert audit.entity_id == str(target.id)
    events = db.query(SecurityAuditEvent).order_by(SecurityAuditEvent.id).all()
    assert [(event.event_type, event.actor_user_id) for event in events] == [
        ("session_created", admin.id),
        ("session_revoked", admin.id),
        ("session_created", admin.id),
    ]


def test_admin_can_impersonate_inactive_unclaimed_target(db, api_client):
    admin, target, _ = _create_users(
        db,
        target_active=False,
        target_claimed=False,
    )
    _authenticate(db, api_client, admin)

    response = api_client.post(f"/api/v1/users/{target.id}/impersonate")
    session_response = api_client.get("/api/v1/auth/session")

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert response.json()["is_claimed"] is False
    assert session_response.status_code == 200
    assert session_response.json()["id"] == target.id
    assert session_response.json()["impersonated_by_username"] == admin.username


def test_impersonated_target_cannot_use_admin_endpoints_but_keeps_gameplay_identity(
    db,
    api_client,
):
    admin, target, _ = _create_users(db)
    _authenticate(db, api_client, admin)
    assert api_client.post(
        f"/api/v1/users/{target.id}/impersonate"
    ).status_code == 200

    admin_response = api_client.get("/api/v1/admin/overview")
    current_response = api_client.get("/api/v1/auth/session")

    assert admin_response.status_code == 403
    assert current_response.status_code == 200
    assert current_response.json()["id"] == target.id


def test_nested_impersonation_is_rejected_without_rotating_session(db, api_client):
    admin, target, user_role = _create_users(db)
    target.role = admin.role
    second_target = User(
        username="FoxSer",
        email="foxser@example.test",
        is_active=True,
        is_claimed=True,
        onboarding_completed_at=NOW,
        role=user_role,
    )
    db.add(second_target)
    db.commit()
    _authenticate(db, api_client, admin)
    assert api_client.post(
        f"/api/v1/users/{target.id}/impersonate"
    ).status_code == 200
    first_token = _current_cookie(api_client)

    response = api_client.post(
        f"/api/v1/users/{second_target.id}/impersonate"
    )

    assert response.status_code == 409
    assert _current_cookie(api_client) == first_token
    assert SessionService().resolve(db, first_token, touch=False).user_id == target.id


def test_return_rotates_to_true_admin_and_revokes_every_previous_cookie(db, api_client):
    admin, target, _ = _create_users(db)
    original_token = _authenticate(db, api_client, admin)
    assert api_client.post(
        f"/api/v1/users/{target.id}/impersonate"
    ).status_code == 200
    impersonated_token = _current_cookie(api_client)

    response = api_client.post("/api/v1/auth/impersonation/return")

    assert response.status_code == 200
    assert response.json()["id"] == admin.id
    assert response.json()["username"] == "ActualOperator"
    assert response.json()["is_admin_impersonation"] is False
    assert response.json()["impersonated_by_username"] is None
    restored_token = _current_cookie(api_client)
    assert restored_token not in {original_token, impersonated_token}
    restored = SessionService().resolve(db, restored_token, touch=False)
    assert restored.user_id == admin.id
    assert restored.is_impersonation is False
    for revoked_token in (original_token, impersonated_token):
        with pytest.raises(InvalidSession):
            SessionService().resolve(db, revoked_token, touch=False)

    audits = db.query(AdminAuditLog).order_by(AdminAuditLog.id).all()
    assert [audit.action for audit in audits] == [
        "user_impersonation_started",
        "user_impersonation_returned",
    ]
    assert all(audit.actor_user_id == admin.id for audit in audits)


def test_return_from_self_impersonation_clears_actor_metadata(db, api_client):
    admin, _, _ = _create_users(db)
    _authenticate(db, api_client, admin)

    started = api_client.post(f"/api/v1/users/{admin.id}/impersonate")
    returned = api_client.post("/api/v1/auth/impersonation/return")

    assert started.status_code == 200
    assert started.json()["is_admin_impersonation"] is True
    assert returned.status_code == 200
    assert returned.json()["is_admin_impersonation"] is False
    assert returned.json()["impersonated_by_username"] is None


def test_revoked_impersonation_cookie_cannot_be_replayed(db, api_client):
    admin, target, _ = _create_users(db)
    _authenticate(db, api_client, admin)
    api_client.post(f"/api/v1/users/{target.id}/impersonate")
    stolen_token = _current_cookie(api_client)
    assert api_client.post("/api/v1/auth/impersonation/return").status_code == 200

    with TestClient(app, base_url="https://testserver") as thief:
        thief.cookies.set(
            settings.SESSION_COOKIE_NAME,
            stolen_token,
            domain="testserver.local",
            path="/",
        )
        replay = thief.post("/api/v1/auth/impersonation/return")

    assert replay.status_code == 401
    cookie = _session_cookie(replay)
    assert "max-age=0" in cookie
    assert "httponly" in cookie
    assert "secure" in cookie


def test_start_transition_rolls_back_when_replacement_issue_fails(
    db,
    api_client,
    monkeypatch,
):
    admin, target, _ = _create_users(db)
    original_token = _authenticate(db, api_client, admin)

    def fail_issue(*_args, **_kwargs):
        raise RuntimeError("injected issue failure")

    monkeypatch.setattr(SessionService, "issue", fail_issue)
    response = api_client.post(f"/api/v1/users/{target.id}/impersonate")

    assert response.status_code == 503
    assert _current_cookie(api_client) == original_token
    assert SessionService().resolve(
        db,
        original_token,
        touch=False,
    ).user_id == admin.id
    assert db.query(AdminAuditLog).count() == 0


def test_return_transition_rolls_back_when_admin_issue_fails(
    db,
    api_client,
    monkeypatch,
):
    admin, target, _ = _create_users(db)
    _authenticate(db, api_client, admin)
    api_client.post(f"/api/v1/users/{target.id}/impersonate")
    impersonated_token = _current_cookie(api_client)

    def fail_issue(*_args, **_kwargs):
        raise RuntimeError("injected issue failure")

    monkeypatch.setattr(SessionService, "issue", fail_issue)
    response = api_client.post("/api/v1/auth/impersonation/return")

    assert response.status_code == 503
    assert _current_cookie(api_client) == impersonated_token
    session = SessionService().resolve(db, impersonated_token, touch=False)
    assert session.user_id == target.id
    assert session.impersonated_by_user_id == admin.id
    assert [
        audit.action
        for audit in db.query(AdminAuditLog).order_by(AdminAuditLog.id).all()
    ] == ["user_impersonation_started"]


@pytest.mark.parametrize("actor_state", ["inactive", "demoted", "deleted"])
def test_return_fails_closed_and_clears_cookie_when_actor_is_no_longer_admin(
    db,
    api_client,
    actor_state,
):
    admin, target, user_role = _create_users(db)
    _authenticate(db, api_client, admin)
    api_client.post(f"/api/v1/users/{target.id}/impersonate")

    if actor_state == "inactive":
        admin.is_active = False
    elif actor_state == "demoted":
        admin.role = user_role
    else:
        db.execute(delete(User).where(User.id == admin.id))
    db.commit()
    db.expire_all()

    response = api_client.post("/api/v1/auth/impersonation/return")

    assert response.status_code == 401
    cookie = _session_cookie(response)
    assert "max-age=0" in cookie
    assert "httponly" in cookie
    assert "secure" in cookie


def test_non_admin_and_inactive_admin_cannot_start_impersonation(db, api_client):
    admin, target, _ = _create_users(db)
    admin.role = target.role
    db.commit()
    _authenticate(db, api_client, admin)
    assert api_client.post(
        f"/api/v1/users/{target.id}/impersonate"
    ).status_code == 403

    admin.role = db.query(Role).filter(Role.name == "admin").one()
    admin.is_active = False
    db.commit()
    api_client.cookies.clear()
    _authenticate(db, api_client, admin)
    response = api_client.post(f"/api/v1/users/{target.id}/impersonate")
    assert response.status_code == 401
