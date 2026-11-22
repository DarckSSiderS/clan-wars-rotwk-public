import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.auth_session import SecurityAuditEvent, UserSession
from app.models.role import Role
from app.models.user import User
from app.services.session_service import InvalidSession, SessionService


NOW = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)


def _create_user(
    db,
    username="player",
    *,
    role_name="user",
    is_active=True,
):
    role = db.query(Role).filter(Role.name == role_name).first()
    if role is None:
        role = Role(name=role_name, description=role_name)
        db.add(role)
        db.flush()
    user = User(
        username=username,
        email=f"{username}@example.test",
        hashed_password="unused",
        is_active=is_active,
        is_claimed=True,
        role=role,
    )
    db.add(user)
    db.commit()
    return user


def _as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def test_issue_persists_only_sha256_with_ttl_and_secret_free_audit(db, monkeypatch):
    user = _create_user(db)
    generated_token = "opaque-session-token"
    token_urlsafe_calls = []
    monkeypatch.setattr(settings, "SESSION_TTL_SECONDS", 120)

    def fake_token_urlsafe(size):
        token_urlsafe_calls.append(size)
        return generated_token

    monkeypatch.setattr("app.services.session_service.secrets.token_urlsafe", fake_token_urlsafe)

    issue = SessionService().issue(
        db,
        user,
        ip_address="203.0.113.10",
        user_agent="test-agent",
        now=NOW,
    )

    stored = db.query(UserSession).one()
    audit = db.query(SecurityAuditEvent).one()
    expected_hash = hashlib.sha256(generated_token.encode("utf-8")).hexdigest()

    assert token_urlsafe_calls == [48]
    assert issue.token == generated_token
    assert issue.expires_at == NOW + timedelta(seconds=120)
    assert stored.token_hash == expected_hash
    assert generated_token not in repr(stored.__dict__)
    assert stored.ip_address == "203.0.113.10"
    assert stored.user_agent == "test-agent"
    assert stored.is_impersonation is False
    assert _as_utc(stored.last_seen_at) == NOW
    assert audit.event_type == "session_created"
    assert audit.user_id == user.id
    assert generated_token not in repr(audit.event_metadata)
    assert expected_hash not in repr(audit.event_metadata)


def test_resolve_loads_active_user_and_role_from_exact_token(db):
    user = _create_user(db)
    user_id = user.id
    issue = SessionService().issue(db, user, now=NOW)
    db.expunge_all()

    session = SessionService().resolve(db, issue.token, now=NOW + timedelta(minutes=1))

    assert session.user.id == user_id
    assert session.user.role.name == "user"
    assert getattr(session.user, "_is_admin_impersonation", False) is False
    assert getattr(session.user, "_impersonated_by_username", None) is None


@pytest.mark.parametrize("token", [None, "", "unknown-token"])
def test_resolve_rejects_missing_or_unknown_token(db, token):
    with pytest.raises(InvalidSession):
        SessionService().resolve(db, token, now=NOW)


def test_resolve_rejects_expired_session(db):
    user = _create_user(db)
    issue = SessionService().issue(db, user, now=NOW)

    with pytest.raises(InvalidSession):
        SessionService().resolve(db, issue.token, now=issue.expires_at)


def test_resolve_rejects_revoked_session(db):
    user = _create_user(db)
    issue = SessionService().issue(db, user, now=NOW)
    assert SessionService().revoke(db, issue.token, now=NOW + timedelta(minutes=1)) is True

    with pytest.raises(InvalidSession):
        SessionService().resolve(db, issue.token, now=NOW + timedelta(minutes=2))


def test_resolve_rejects_session_without_user(db):
    token = "orphan-session"
    db.add(
        UserSession(
            user_id=999,
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            created_at=NOW,
            last_seen_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
    )
    db.commit()

    with pytest.raises(InvalidSession):
        SessionService().resolve(db, token, now=NOW)


def test_revoke_is_idempotent_and_audit_contains_no_session_secret(db):
    user = _create_user(db)
    issue = SessionService().issue(db, user, now=NOW)
    service = SessionService()

    assert service.revoke(db, issue.token, now=NOW + timedelta(minutes=1)) is True
    assert service.revoke(db, issue.token, now=NOW + timedelta(minutes=2)) is False

    revoked = db.query(UserSession).one()
    audits = db.query(SecurityAuditEvent).filter_by(event_type="session_revoked").all()
    assert _as_utc(revoked.revoked_at) == NOW + timedelta(minutes=1)
    assert len(audits) == 1
    assert issue.token not in repr(audits[0].event_metadata)
    assert revoked.token_hash not in repr(audits[0].event_metadata)


def test_revoke_all_keeps_except_token_and_reports_revoked_count(db):
    user = _create_user(db)
    service = SessionService()
    kept = service.issue(db, user, now=NOW)
    revoked_one = service.issue(db, user, now=NOW + timedelta(seconds=1))
    revoked_two = service.issue(db, user, now=NOW + timedelta(seconds=2))

    count = service.revoke_all(
        db,
        user.id,
        except_token=kept.token,
        now=NOW + timedelta(minutes=1),
    )

    assert count == 2
    assert service.resolve(db, kept.token, now=NOW + timedelta(minutes=2)).user_id == user.id
    with pytest.raises(InvalidSession):
        service.resolve(db, revoked_one.token, now=NOW + timedelta(minutes=2))
    with pytest.raises(InvalidSession):
        service.resolve(db, revoked_two.token, now=NOW + timedelta(minutes=2))
    audit = db.query(SecurityAuditEvent).filter_by(event_type="sessions_revoked_all").one()
    assert audit.event_metadata == {"revoked_count": 2, "kept_current": True}
    for secret in (kept.token, revoked_one.token, revoked_two.token):
        assert secret not in repr(audit.event_metadata)


def test_resolve_rejects_inactive_effective_user(db):
    user = _create_user(db, is_active=False)
    issue = SessionService().issue(db, user, now=NOW)

    with pytest.raises(InvalidSession):
        SessionService().resolve(db, issue.token, now=NOW)


def test_active_admin_impersonation_may_resolve_inactive_effective_user(db):
    admin = _create_user(db, "administrator", role_name="admin")
    target = _create_user(db, "blocked-player", is_active=False)
    issue = SessionService().issue(
        db,
        target,
        impersonated_by_user_id=admin.id,
        now=NOW,
    )

    session = SessionService().resolve(db, issue.token, now=NOW)

    assert session.user.id == target.id
    assert session.is_impersonation is True
    assert session.user._is_admin_impersonation is True
    assert session.user._impersonated_by_username == admin.username


@pytest.mark.parametrize(
    ("actor_role", "actor_active"),
    [("user", True), ("admin", False)],
)
def test_resolve_rejects_unauthorized_impersonation_actor(db, actor_role, actor_active):
    actor = _create_user(
        db,
        f"actor-{actor_role}-{actor_active}",
        role_name=actor_role,
        is_active=actor_active,
    )
    target = _create_user(db, "target")
    issue = SessionService().issue(
        db,
        target,
        impersonated_by_user_id=actor.id,
        now=NOW,
    )

    with pytest.raises(InvalidSession):
        SessionService().resolve(db, issue.token, now=NOW)

    db.expire_all()
    assert _as_utc(db.query(UserSession).one().revoked_at) == NOW


def test_resolve_rejects_missing_impersonation_actor(db):
    target = _create_user(db)
    issue = SessionService().issue(
        db,
        target,
        impersonated_by_user_id=999,
        now=NOW,
    )

    with pytest.raises(InvalidSession):
        SessionService().resolve(db, issue.token, now=NOW)

    db.expire_all()
    stored = db.query(UserSession).one()
    assert stored.is_impersonation is True
    assert stored.impersonated_by_user_id == 999
    assert _as_utc(stored.revoked_at) == NOW


def test_resolve_revokes_actor_reference_without_impersonation_marker(db):
    admin = _create_user(db, "marker-admin", role_name="admin")
    target = _create_user(db, "marker-target")
    issue = SessionService().issue(db, target, now=NOW)
    stored = db.query(UserSession).one()
    stored.impersonated_by_user_id = admin.id
    stored.is_impersonation = False
    db.commit()

    with pytest.raises(InvalidSession):
        SessionService().resolve(db, issue.token, now=NOW)

    db.expire_all()
    assert _as_utc(db.query(UserSession).one().revoked_at) == NOW


def test_resolve_touches_last_seen_at_at_most_once_per_five_minutes(db):
    user = _create_user(db)
    service = SessionService()
    issue = service.issue(db, user, now=NOW)

    service.resolve(db, issue.token, now=NOW + timedelta(minutes=4, seconds=59))
    stored = db.query(UserSession).one()
    assert _as_utc(stored.last_seen_at) == NOW

    service.resolve(db, issue.token, now=NOW + timedelta(minutes=5))
    db.refresh(stored)
    assert _as_utc(stored.last_seen_at) == NOW + timedelta(minutes=5)


def test_touch_allows_only_one_conditional_update_from_stale_sessions(db):
    user = _create_user(db)
    issue = SessionService().issue(db, user, now=NOW)
    session_id = db.query(UserSession.id).one()[0]
    session_factory = sessionmaker(bind=db.get_bind())
    first_db = session_factory()
    second_db = session_factory()
    try:
        first_copy = first_db.get(UserSession, session_id)
        second_copy = second_db.get(UserSession, session_id)
        assert _as_utc(first_copy.last_seen_at) == NOW
        assert _as_utc(second_copy.last_seen_at) == NOW

        service = SessionService()
        assert service.touch(
            first_db,
            first_copy,
            now=NOW + timedelta(minutes=5),
        ) is True
        assert service.touch(
            second_db,
            second_copy,
            now=NOW + timedelta(minutes=5, seconds=1),
        ) is False
    finally:
        first_db.close()
        second_db.close()

    db.expire_all()
    stored = db.get(UserSession, session_id)
    assert _as_utc(stored.last_seen_at) == NOW + timedelta(minutes=5)
    assert SessionService().resolve(db, issue.token, now=NOW + timedelta(minutes=6))
