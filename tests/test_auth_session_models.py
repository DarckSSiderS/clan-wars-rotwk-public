import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.models import (
    OAuthLoginState,
    Role,
    SecurityAuditEvent,
    User,
    UserSession,
)
from app.services.session_service import InvalidSession, SessionService


def test_oauth_session_models_persist_defaults_and_relationships(db):
    user = User(username="arena-player", email=None)
    administrator = User(username="administrator", email=None)
    db.add_all([user, administrator])
    db.flush()

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    login_state = OAuthLoginState(
        state_hash="state-hash",
        flow_hash="flow-hash",
        expires_at=expires_at,
    )
    session = UserSession(
        user=user,
        token_hash="token-hash",
        expires_at=expires_at,
        is_impersonation=True,
        impersonated_by_user=administrator,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    ordinary_session = UserSession(
        user=user,
        token_hash="ordinary-token-hash",
        expires_at=expires_at,
    )
    audit_event = SecurityAuditEvent(
        user=user,
        actor_user=administrator,
        event_type="login",
    )
    db.add_all([login_state, session, ordinary_session, audit_event])
    db.commit()
    db.expire_all()

    saved_user = db.query(User).filter_by(username="arena-player").one()
    assert saved_user.email is None
    assert saved_user.onboarding_completed_at is None
    assert saved_user.history_mode is None
    assert saved_user.statistics_started_at is None
    saved_impersonation = db.query(UserSession).filter_by(token_hash="token-hash").one()
    saved_ordinary = db.query(UserSession).filter_by(token_hash="ordinary-token-hash").one()
    assert saved_impersonation.is_impersonation is True
    assert saved_ordinary.is_impersonation is False
    assert saved_user.security_audit_events[0].event_type == "login"
    assert administrator.impersonated_sessions[0].user_id == saved_user.id
    assert administrator.acted_security_audit_events[0].user_id == saved_user.id
    assert db.query(OAuthLoginState).one().return_to == "/"
    assert db.query(SecurityAuditEvent).one().event_metadata == {}


def test_deleting_impersonation_actor_cascades_session_with_foreign_keys(db):
    db.execute(text("PRAGMA foreign_keys=ON"))
    role = Role(id=2, name="cascade-user", description="User")
    target = User(username="cascade-target", email=None, role=role)
    administrator = User(
        username="cascade-administrator",
        email=None,
        role=role,
    )
    db.add_all([role, target, administrator])
    db.flush()
    token = "cascade-token"
    db.add(
        UserSession(
            user=target,
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            is_impersonation=True,
            impersonated_by_user=administrator,
        )
    )
    db.commit()

    foreign_key = next(
        item
        for item in inspect(db.get_bind()).get_foreign_keys("user_sessions")
        if item["constrained_columns"] == ["impersonated_by_user_id"]
    )
    assert foreign_key["options"]["ondelete"] == "CASCADE"

    db.delete(administrator)
    db.commit()

    assert db.query(UserSession).filter_by(
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest()
    ).first() is None
    with pytest.raises(InvalidSession):
        SessionService().resolve(db, token, touch=False)


@pytest.mark.parametrize("field", ["state_hash", "token_hash"])
def test_oauth_state_and_session_hashes_are_unique(db, field):
    user = User(username=f"{field}-user", email=None)
    db.add(user)
    db.flush()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    if field == "state_hash":
        first = OAuthLoginState(
            state_hash="duplicate",
            flow_hash="flow-1",
            expires_at=expires_at,
        )
        second = OAuthLoginState(
            state_hash="duplicate",
            flow_hash="flow-2",
            expires_at=expires_at,
        )
    else:
        first = UserSession(
            user_id=user.id,
            token_hash="duplicate",
            expires_at=expires_at,
        )
        second = UserSession(
            user_id=user.id,
            token_hash="duplicate",
            expires_at=expires_at,
        )

    db.add(first)
    db.commit()
    db.add(second)
    with pytest.raises(IntegrityError):
        db.commit()
