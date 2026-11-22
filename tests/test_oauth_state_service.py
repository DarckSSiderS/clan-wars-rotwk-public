from datetime import datetime, timedelta, timezone
import hashlib

import pytest

from app.config import settings
from app.models import OAuthLoginState
from app.services.oauth_state_service import InvalidOAuthState, OAuthStateService


def as_utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def test_issue_stores_only_hashes_and_returns_authorize_parameters(db, monkeypatch):
    monkeypatch.setattr(settings, "BFME_OAUTH_CLIENT_ID", "arena-client")
    monkeypatch.setattr(
        settings,
        "BFME_OAUTH_REDIRECT_URI",
        "https://arena.example/auth/callback",
    )
    now = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)

    issued = OAuthStateService().issue(db, "/wars/42", now)

    saved = db.query(OAuthLoginState).one()
    assert saved.state_hash == hashlib.sha256(issued.state.encode()).hexdigest()
    assert saved.flow_hash == hashlib.sha256(issued.flow_token.encode()).hexdigest()
    assert saved.state_hash != issued.state
    assert saved.flow_hash != issued.flow_token
    assert saved.return_to == "/wars/42"
    assert as_utc(saved.expires_at) == now + timedelta(
        seconds=settings.BFME_OAUTH_STATE_TTL_SECONDS
    )
    assert issued.authorize_params == {
        "client_id": "arena-client",
        "redirect_uri": "https://arena.example/auth/callback",
        "state": issued.state,
    }


@pytest.mark.parametrize("return_to", ["/", "/wars/42?tab=members", "/profile#about"])
def test_issue_preserves_safe_local_return_path(db, return_to):
    issued = OAuthStateService().issue(db, return_to)

    assert db.query(OAuthLoginState).one().return_to == return_to
    assert issued.state


@pytest.mark.parametrize(
    "return_to",
    [
        "https://attacker.example/steal",
        "//attacker.example/steal",
        "/\\attacker.example/steal",
        "/next\nSet-Cookie: stolen",
        "relative/path",
    ],
)
def test_issue_replaces_unsafe_return_path_with_root(db, return_to):
    OAuthStateService().issue(db, return_to)

    assert db.query(OAuthLoginState).one().return_to == "/"


def test_consume_marks_matching_unexpired_state_as_consumed(db):
    service = OAuthStateService()
    now = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    issued = service.issue(db, "/wars/42", now)

    consumed = service.consume(db, issued.state, issued.flow_token, now)

    assert consumed.return_to == "/wars/42"
    assert as_utc(consumed.consumed_at) == now
    assert as_utc(db.query(OAuthLoginState).one().consumed_at) == now


def test_consume_rejects_replayed_state(db):
    service = OAuthStateService()
    now = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    issued = service.issue(db, "/", now)
    service.consume(db, issued.state, issued.flow_token, now)

    with pytest.raises(InvalidOAuthState):
        service.consume(db, issued.state, issued.flow_token, now)


def test_consume_rejects_wrong_flow_token(db):
    service = OAuthStateService()
    issued = service.issue(db, "/")

    with pytest.raises(InvalidOAuthState):
        service.consume(db, issued.state, "wrong-flow-token")


def test_consume_rejects_unknown_state(db):
    with pytest.raises(InvalidOAuthState):
        OAuthStateService().consume(db, "unknown-state", "unknown-flow")


def test_consume_rejects_expired_state_with_naive_sqlite_datetime(db):
    service = OAuthStateService()
    issued_at = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    issued = service.issue(db, "/", issued_at)
    db.expire_all()

    with pytest.raises(InvalidOAuthState):
        service.consume(
            db,
            issued.state,
            issued.flow_token,
            issued_at + timedelta(seconds=settings.BFME_OAUTH_STATE_TTL_SECONDS),
        )
