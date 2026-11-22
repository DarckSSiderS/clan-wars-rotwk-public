from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi.testclient import TestClient

import app.api.v1.oauth as oauth_api
from app.api.v1.oauth import (
    get_account_onboarding_service,
    get_arena_match_backfill_service,
    get_bfme_oauth_service,
    get_session_service,
)
from app.config import settings
from app.core.security import get_password_hash, verify_password
from app.database import get_db
from app.main import app
from app.models.auth_session import (
    OAuthLoginState,
    SecurityAuditEvent,
    UserSession,
)
from app.models.external_identity import (
    ExternalPlayerAlias,
    ExternalPlayerIdentity,
)
from app.models.role import Role
from app.models.user import User
from app.services.account_onboarding_service import AccountIdentityConflict
from app.services.bfme_oauth_service import (
    ArenaIdentity,
    ArenaOAuthRejected,
    ArenaOAuthUnavailable,
)
from app.services.session_service import SessionService


class FakeArenaOAuthService:
    def __init__(self):
        self.identity = ArenaIdentity(
            uuid="arena-user-uuid",
            display_name="ArenaPlayer",
        )
        self.exchange_error = None
        self.identity_error = None
        self.authorize_states = []
        self.exchanged_codes = []
        self.fetched_tokens = []

    def build_authorize_url(self, state):
        self.authorize_states.append(state)
        return "https://arena.example/oauth/authorize?" + urlencode(
            {"state": state, "client_id": "public-client"}
        )

    async def exchange_code(self, code):
        self.exchanged_codes.append(code)
        if self.exchange_error is not None:
            raise self.exchange_error
        return "arena-access-token-secret"

    async def fetch_identity(self, access_token):
        self.fetched_tokens.append(access_token)
        if self.identity_error is not None:
            raise self.identity_error
        return self.identity


class FakeArenaMatchBackfillService:
    def __init__(self):
        self.queued_user_ids = []
        self.processed_job_ids = []

    def ensure_queued(self, db, user):
        self.queued_user_ids.append(user.id)
        return type("BackfillJob", (), {"id": user.id})(), True

    async def process_job_by_id(self, job_id):
        self.processed_job_ids.append(job_id)
        return True


@pytest.fixture()
def enabled_oauth(monkeypatch):
    monkeypatch.setattr(settings, "BFME_OAUTH_ENABLED", True)
    monkeypatch.setattr(settings, "BFME_OAUTH_CLIENT_ID", "public-client")
    monkeypatch.setattr(
        settings,
        "BFME_OAUTH_REDIRECT_URI",
        "https://clanwars.example/api/v1/auth/arena/callback",
    )
    monkeypatch.setattr(settings, "BFME_OAUTH_STATE_TTL_SECONDS", 173)
    monkeypatch.setattr(settings, "SESSION_TTL_SECONDS", 7211)


@pytest.fixture()
def arena_backfill_service():
    service = FakeArenaMatchBackfillService()
    app.dependency_overrides[get_arena_match_backfill_service] = lambda: service
    try:
        yield service
    finally:
        app.dependency_overrides.pop(get_arena_match_backfill_service, None)


@pytest.fixture()
def arena_service(arena_backfill_service):
    service = FakeArenaOAuthService()
    app.dependency_overrides[get_bfme_oauth_service] = lambda: service
    try:
        yield service
    finally:
        app.dependency_overrides.pop(get_bfme_oauth_service, None)


@pytest.fixture()
def api_client(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app, base_url="https://testserver") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _start_oauth(client, return_to="/"):
    response = client.get(
        "/api/v1/auth/arena/start",
        params={"return_to": return_to},
        follow_redirects=False,
    )
    assert response.status_code == 302
    state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    return response, state


def _set_flow_cookie(client, value):
    client.cookies.set(
        settings.OAUTH_FLOW_COOKIE_NAME,
        value,
        domain="testserver.local",
        path="/",
    )


def _cookie_headers(response):
    return [value.lower() for value in response.headers.get_list("set-cookie")]


def _authenticate_client(db, client, user):
    issue = SessionService().issue(db, user)
    client.cookies.set(
        settings.SESSION_COOKIE_NAME,
        issue.token,
        domain="testserver.local",
        path="/",
    )
    return issue.token


def _create_arena_user(
    db,
    *,
    external_uuid="arena-user-uuid",
    current_nickname="ArenaPlayer",
    username="internal-player",
    is_active=True,
    is_claimed=True,
    onboarding_completed_at=None,
    hashed_password=None,
):
    now = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    user = User(
        username=username,
        display_name=current_nickname,
        email=None,
        hashed_password=hashed_password,
        is_active=is_active,
        is_claimed=is_claimed,
        onboarding_completed_at=onboarding_completed_at,
    )
    identity = ExternalPlayerIdentity(
        user=user,
        source="bfmeladder",
        external_uuid=external_uuid,
        current_nickname=current_nickname,
        verification_status="verified",
        claimed_at=now,
        verified_at=now,
        first_seen_at=now,
        last_seen_at=now,
    )
    identity.aliases.append(
        ExternalPlayerAlias(
            nickname=current_nickname,
            first_seen_at=now,
            last_seen_at=now,
        )
    )
    db.add(user)
    db.commit()
    return user


def test_oauth_start_returns_machine_readable_503_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "BFME_OAUTH_ENABLED", False)

    with TestClient(app, base_url="https://testserver") as client:
        response = client.get(
            "/api/v1/auth/arena/start",
            follow_redirects=False,
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": {"code": "oauth_not_configured"},
    }
    assert settings.OAUTH_FLOW_COOKIE_NAME not in response.headers.get(
        "set-cookie",
        "",
    )


def test_retired_auth_endpoints_are_not_routable(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app, base_url="https://testserver") as client:
            responses = (
                client.post("/api/v1/auth/token"),
                client.post("/api/v1/auth/register", json={}),
                client.get("/api/v1/auth/registration-status/OldNick"),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert [response.status_code for response in responses] == [404, 404, 404]


def test_oauth_start_sets_bound_flow_cookie_and_uses_client_redirect(
    db,
    api_client,
    arena_service,
    enabled_oauth,
):
    response, state = _start_oauth(api_client, "/wars/7?tab=map")

    login_state = db.query(OAuthLoginState).one()
    flow_token = api_client.cookies.get(settings.OAUTH_FLOW_COOKIE_NAME)
    cookie = _cookie_headers(response)[0]
    assert response.status_code == 302
    assert response.headers["location"].startswith(
        "https://arena.example/oauth/authorize?"
    )
    assert arena_service.authorize_states == [state]
    assert sha256(state.encode()).hexdigest() == login_state.state_hash
    assert sha256(flow_token.encode()).hexdigest() == login_state.flow_hash
    assert login_state.return_to == "/wars/7?tab=map"
    assert f"max-age={settings.BFME_OAUTH_STATE_TTL_SECONDS}" in cookie
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie


def test_oauth_callback_creates_new_user_session_without_exposing_secrets(
    db,
    api_client,
    arena_service,
    arena_backfill_service,
    enabled_oauth,
):
    start_response, state = _start_oauth(api_client, "/wars/7")
    flow_token = api_client.cookies.get(settings.OAUTH_FLOW_COOKIE_NAME)

    response = api_client.get(
        "/api/v1/auth/arena/callback",
        params={"code": "authorization-code-secret", "state": state},
        follow_redirects=False,
    )

    cookies = _cookie_headers(response)
    session_cookie = next(
        value
        for value in cookies
        if value.startswith(settings.SESSION_COOKIE_NAME.lower() + "=")
    )
    flow_cookie = next(
        value
        for value in cookies
        if value.startswith(settings.OAUTH_FLOW_COOKIE_NAME.lower() + "=")
    )
    assert start_response.status_code == 302
    assert response.status_code == 302
    assert response.headers["location"] == "/onboarding"
    assert arena_service.exchanged_codes == ["authorization-code-secret"]
    assert arena_service.fetched_tokens == ["arena-access-token-secret"]
    assert db.query(User).count() == 1
    assert db.query(UserSession).count() == 1
    user = db.query(User).one()
    assert arena_backfill_service.queued_user_ids == [user.id]
    assert arena_backfill_service.processed_job_ids == [user.id]
    assert sha256(flow_token.encode()).hexdigest() == (
        db.query(OAuthLoginState).one().flow_hash
    )
    assert f"max-age={settings.SESSION_TTL_SECONDS}" in session_cookie
    assert "httponly" in session_cookie
    assert "secure" in session_cookie
    assert "samesite=lax" in session_cookie
    assert "path=/" in session_cookie
    assert "max-age=0" in flow_cookie
    assert "authorization-code-secret" not in response.text
    assert "arena-access-token-secret" not in response.text
    assert "authorization-code-secret" not in response.headers["location"]
    assert "arena-access-token-secret" not in response.headers["location"]


def test_completed_oauth_user_returns_only_to_consumed_local_path(
    db,
    api_client,
    arena_service,
    enabled_oauth,
):
    _create_arena_user(
        db,
        onboarding_completed_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )
    _, state = _start_oauth(api_client, "/wars/7?tab=map")

    response = api_client.get(
        "/api/v1/auth/arena/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/wars/7?tab=map"
    assert db.query(User).count() == 1


def test_oauth_callback_never_redirects_to_external_return_target(
    db,
    api_client,
    arena_service,
    enabled_oauth,
):
    _create_arena_user(
        db,
        onboarding_completed_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )
    _, state = _start_oauth(api_client, "https://evil.example/steal")

    response = api_client.get(
        "/api/v1/auth/arena/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/"


def test_oauth_state_replay_is_rejected_before_second_exchange(
    db,
    api_client,
    arena_service,
    enabled_oauth,
):
    _, state = _start_oauth(api_client)
    flow_token = api_client.cookies.get(settings.OAUTH_FLOW_COOKIE_NAME)
    first = api_client.get(
        "/api/v1/auth/arena/callback",
        params={"code": "first-code", "state": state},
        follow_redirects=False,
    )
    _set_flow_cookie(api_client, flow_token)

    replay = api_client.get(
        "/api/v1/auth/arena/callback",
        params={"code": "replay-code", "state": state},
        follow_redirects=False,
    )

    assert first.status_code == 302
    assert replay.status_code == 302
    assert replay.headers["location"] == "/login?oauth_error=invalid_state"
    assert arena_service.exchanged_codes == ["first-code"]
    assert db.query(UserSession).count() == 1
    assert any("max-age=0" in value for value in _cookie_headers(replay))


def test_arena_denial_clears_flow_without_session_or_reflected_description(
    db,
    api_client,
    arena_service,
    enabled_oauth,
):
    _, state = _start_oauth(api_client)

    response = api_client.get(
        "/api/v1/auth/arena/callback",
        params={
            "error": "access_denied",
            "error_description": "client_secret=must-not-leak",
            "state": state,
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/login?oauth_error=access_denied"
    assert "must-not-leak" not in response.text
    assert db.query(UserSession).count() == 0
    assert db.query(OAuthLoginState).one().consumed_at is None
    assert arena_service.exchanged_codes == []
    assert any("max-age=0" in value for value in _cookie_headers(response))


@pytest.mark.parametrize("missing", ["code", "state", "cookie"])
def test_oauth_callback_rejects_missing_flow_inputs(
    db,
    api_client,
    arena_service,
    enabled_oauth,
    missing,
):
    _, state = _start_oauth(api_client)
    params = {"code": "valid-code", "state": state}
    if missing in params:
        del params[missing]
    if missing == "cookie":
        api_client.cookies.clear()

    response = api_client.get(
        "/api/v1/auth/arena/callback",
        params=params,
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == (
        "/login?oauth_error=invalid_callback"
    )
    assert arena_service.exchanged_codes == []
    assert db.query(UserSession).count() == 0
    assert any("max-age=0" in value for value in _cookie_headers(response))


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (
            ArenaOAuthUnavailable("client_secret=must-not-leak"),
            "arena_unavailable",
        ),
        (
            ArenaOAuthRejected("authorization-code-secret"),
            "arena_rejected",
        ),
    ],
)
def test_oauth_callback_sanitizes_arena_failures(
    db,
    api_client,
    arena_service,
    enabled_oauth,
    failure,
    expected_code,
):
    arena_service.exchange_error = failure
    _, state = _start_oauth(api_client)

    response = api_client.get(
        "/api/v1/auth/arena/callback",
        params={"code": "authorization-code-secret", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == (
        f"/login?oauth_error={expected_code}"
    )
    assert "must-not-leak" not in response.text
    assert "authorization-code-secret" not in response.text
    assert db.query(OAuthLoginState).one().consumed_at is not None
    assert db.query(UserSession).count() == 0
    assert any("max-age=0" in value for value in _cookie_headers(response))


def test_oauth_callback_rejects_blocked_existing_account(
    db,
    api_client,
    arena_service,
    enabled_oauth,
):
    _create_arena_user(db, is_active=False)
    _, state = _start_oauth(api_client)

    response = api_client.get(
        "/api/v1/auth/arena/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == (
        "/login?oauth_error=inactive_account"
    )
    assert db.query(UserSession).count() == 0


def test_oauth_callback_rejects_invalid_identity_without_partial_account(
    db,
    api_client,
    arena_service,
    enabled_oauth,
):
    arena_service.identity = ArenaIdentity(
        uuid="uuid-without-name",
        display_name="",
    )
    _, state = _start_oauth(api_client)

    response = api_client.get(
        "/api/v1/auth/arena/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == (
        "/login?oauth_error=invalid_identity"
    )
    assert db.query(User).count() == 0
    assert db.query(UserSession).count() == 0


def test_oauth_callback_sanitizes_identity_fetch_failure_and_clears_flow(
    db,
    api_client,
    arena_service,
    enabled_oauth,
):
    arena_service.identity_error = ArenaOAuthUnavailable(
        "identity endpoint secret detail"
    )
    _, state = _start_oauth(api_client)

    response = api_client.get(
        "/api/v1/auth/arena/callback",
        params={"code": "identity-fetch-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == (
        "/login?oauth_error=arena_unavailable"
    )
    assert arena_service.exchanged_codes == ["identity-fetch-code"]
    assert arena_service.fetched_tokens == ["arena-access-token-secret"]
    assert "identity endpoint secret detail" not in response.text
    assert db.query(OAuthLoginState).one().consumed_at is not None
    assert db.query(UserSession).count() == 0
    assert any("max-age=0" in value for value in _cookie_headers(response))


def test_disabled_oauth_callback_has_stable_error_and_clears_flow(
    db,
    api_client,
    arena_service,
    monkeypatch,
):
    monkeypatch.setattr(settings, "BFME_OAUTH_ENABLED", False)
    _set_flow_cookie(api_client, "disabled-flow-token")

    response = api_client.get(
        "/api/v1/auth/arena/callback",
        params={"code": "disabled-code", "state": "disabled-state"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == (
        "/login?oauth_error=oauth_not_configured"
    )
    assert arena_service.exchanged_codes == []
    assert db.query(UserSession).count() == 0
    assert any("max-age=0" in value for value in _cookie_headers(response))


class ConflictingAccountOnboardingService:
    def get_or_create_arena_user(self, db, external_uuid, display_name):
        raise AccountIdentityConflict("conflict secret detail")


def test_oauth_callback_sanitizes_account_conflict_and_clears_flow(
    db,
    api_client,
    arena_service,
    enabled_oauth,
):
    service = ConflictingAccountOnboardingService()
    app.dependency_overrides[get_account_onboarding_service] = lambda: service
    try:
        _, state = _start_oauth(api_client)
        response = api_client.get(
            "/api/v1/auth/arena/callback",
            params={"code": "conflict-code", "state": state},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.pop(get_account_onboarding_service, None)

    assert response.status_code == 302
    assert response.headers["location"] == (
        "/login?oauth_error=account_conflict"
    )
    assert "conflict secret detail" not in response.text
    assert db.query(UserSession).count() == 0
    assert any("max-age=0" in value for value in _cookie_headers(response))


def test_oauth_callback_sanitizes_unexpected_failure_and_clears_flow(
    db,
    api_client,
    arena_service,
    enabled_oauth,
):
    arena_service.exchange_error = RuntimeError("unexpected secret detail")
    _, state = _start_oauth(api_client)

    response = api_client.get(
        "/api/v1/auth/arena/callback",
        params={"code": "unexpected-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/login?oauth_error=oauth_failed"
    assert "unexpected secret detail" not in response.text
    assert db.query(OAuthLoginState).one().consumed_at is not None
    assert db.query(UserSession).count() == 0
    assert any("max-age=0" in value for value in _cookie_headers(response))


def test_non_denial_arena_error_is_stable_and_clears_flow(
    db,
    api_client,
    arena_service,
    enabled_oauth,
):
    _set_flow_cookie(api_client, "arena-error-flow-token")

    response = api_client.get(
        "/api/v1/auth/arena/callback",
        params={
            "error": "temporarily_unavailable",
            "error_description": "external secret description",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == (
        "/login?oauth_error=arena_rejected"
    )
    assert "external secret description" not in response.text
    assert arena_service.exchanged_codes == []
    assert db.query(UserSession).count() == 0
    audit = db.query(SecurityAuditEvent).order_by(SecurityAuditEvent.id.desc()).first()
    assert audit.event_metadata["reason"] == (
        "arena_rejected:callback:temporarily_unavailable"
    )
    assert any("max-age=0" in value for value in _cookie_headers(response))


def test_session_returns_authenticated_summary_and_onboarding_flag(
    db,
    api_client,
):
    role = Role(
        id=1,
        name="admin",
        description="Project administrator",
    )
    db.add(role)
    user = _create_arena_user(db, current_nickname="SessionPlayer")
    user.role = role
    user.balance = 730
    user.level = 4
    user.experience = 1250
    user.avatar_url = "/images/users/session-player.png"
    user.allow_clan_invites = False
    user.telegram_url = "https://t.me/session_player"
    user.twitch_url = "https://twitch.tv/session_player"
    user.youtube_url = "https://youtube.com/@session_player"
    db.commit()
    _authenticate_client(db, api_client, user)

    response = api_client.get("/api/v1/auth/session")

    assert response.status_code == 200
    assert response.json() == {
        "id": user.id,
        "username": "internal-player",
        "display_name": "SessionPlayer",
        "email": None,
        "is_active": True,
        "is_claimed": True,
        "balance": 730,
        "level": 4,
        "experience": 1250,
        "avatar_url": "/images/users/session-player.png",
        "language": "ru",
        "allow_clan_invites": False,
        "telegram_url": "https://t.me/session_player",
        "twitch_url": "https://twitch.tv/session_player",
        "youtube_url": "https://youtube.com/@session_player",
        "role": {
            "id": 1,
            "name": "admin",
            "description": "Project administrator",
        },
        "created_at": user.created_at.isoformat(),
        "onboarding_completed_at": None,
        "history_mode": None,
        "statistics_started_at": None,
        "external_identity_status": "verified",
        "is_admin_impersonation": False,
        "impersonated_by_username": None,
        "onboarding_required": True,
    }
    assert "hashed_password" not in response.text
    assert "arena-user-uuid" not in response.text


@pytest.mark.parametrize("session_token", [None, "invalid-session-token"])
def test_session_rejects_missing_or_invalid_cookie(
    api_client,
    session_token,
):
    if session_token is not None:
        api_client.cookies.set(
            settings.SESSION_COOKIE_NAME,
            session_token,
            domain="testserver.local",
            path="/",
        )

    response = api_client.get("/api/v1/auth/session")

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "invalid_session"}}
    assert "www-authenticate" not in response.headers


def test_onboarding_completes_active_user_and_returns_updated_summary(
    db,
    api_client,
):
    user = _create_arena_user(db, current_nickname="NewPlayer")
    _authenticate_client(db, api_client, user)

    response = api_client.post(
        "/api/v1/auth/onboarding",
        json={
            "history_mode": "new",
            "language": "de",
            "accepted_rules": True,
            "password": "strong-local-password",
        },
    )

    db.refresh(user)
    payload = response.json()
    assert response.status_code == 200
    assert payload["id"] == user.id
    assert payload["language"] == "de"
    assert payload["history_mode"] == "new"
    assert payload["onboarding_required"] is False
    assert payload["onboarding_completed_at"] is not None
    assert payload["statistics_started_at"] is not None
    assert user.hashed_password is not None
    assert "strong-local-password" not in response.text
    assert user.hashed_password not in response.text


def test_onboarding_rotates_session_and_invalidates_pre_onboarding_token(
    db,
    api_client,
):
    user = _create_arena_user(db, current_nickname="RotatePlayer")
    old_token = _authenticate_client(db, api_client, user)

    response = api_client.post(
        "/api/v1/auth/onboarding",
        json={
            "history_mode": "new",
            "language": "ru",
            "accepted_rules": True,
        },
    )
    new_token = api_client.cookies.get(settings.SESSION_COOKIE_NAME)

    assert response.status_code == 200
    assert new_token
    assert new_token != old_token
    db.expire_all()
    sessions = db.query(UserSession).order_by(UserSession.id).all()
    assert len(sessions) == 2
    assert sessions[0].revoked_at is not None
    assert sessions[1].revoked_at is None

    api_client.cookies.clear()
    api_client.cookies.set(
        settings.SESSION_COOKIE_NAME,
        old_token,
        domain="testserver.local",
        path="/",
    )
    old_session = api_client.get("/api/v1/auth/session")
    api_client.cookies.clear()
    api_client.cookies.set(
        settings.SESSION_COOKIE_NAME,
        new_token,
        domain="testserver.local",
        path="/",
    )
    new_session = api_client.get("/api/v1/auth/session")

    assert old_session.status_code == 401
    assert new_session.status_code == 200
    assert new_session.json()["id"] == user.id


class FailingAfterIssueSessionService(SessionService):
    def issue(self, db, user, **kwargs):
        kwargs["commit"] = False
        super().issue(db, user, **kwargs)
        raise RuntimeError("rotation failure secret")


def test_onboarding_rotation_failure_rolls_back_entire_transition(db):
    user = _create_arena_user(
        db,
        current_nickname="AtomicPlayer",
        username="atomic-player",
    )
    user_id = user.id
    with TestClient(
        app,
        base_url="https://testserver",
        raise_server_exceptions=False,
    ) as client:
        old_token = _authenticate_client(db, client, user)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_session_service] = (
            lambda: FailingAfterIssueSessionService()
        )
        try:
            response = client.post(
                "/api/v1/auth/onboarding",
                json={
                    "history_mode": "new",
                    "language": "de",
                    "accepted_rules": True,
                    "password": "atomic-local-password",
                },
            )
        finally:
            app.dependency_overrides.pop(get_session_service, None)
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 503
        assert response.json() == {
            "detail": {"code": "session_transition_failed"}
        }
        assert "rotation failure secret" not in response.text
        assert not _cookie_headers(response)
        assert client.cookies.get(settings.SESSION_COOKIE_NAME) == old_token

        db.expire_all()
        saved_user = db.get(User, user_id)
        sessions = db.query(UserSession).all()
        assert saved_user.onboarding_completed_at is None
        assert saved_user.history_mode is None
        assert saved_user.statistics_started_at is None
        assert saved_user.hashed_password is None
        assert len(sessions) == 1
        assert sessions[0].revoked_at is None
        resolved = SessionService().resolve(db, old_token, touch=False)

    assert resolved.user_id == user_id
    assert resolved.user.onboarding_completed_at is None


class CountingOnboardingService:
    def __init__(self):
        self.calls = 0
        self.commit_values = []

    def complete_onboarding(
        self,
        db,
        user,
        history_mode,
        language,
        accepted_rules,
        password=None,
        commit=True,
    ):
        self.calls += 1
        self.commit_values.append(commit)
        completed_at = datetime(2026, 8, 22, 14, 0, tzinfo=timezone.utc)
        user.history_mode = history_mode
        user.language = language
        user.onboarding_completed_at = completed_at
        user.statistics_started_at = completed_at
        return user


def test_onboarding_endpoint_calls_injected_service_exactly_once(
    db,
    api_client,
):
    user = _create_arena_user(db)
    _authenticate_client(db, api_client, user)
    service = CountingOnboardingService()
    app.dependency_overrides[get_account_onboarding_service] = lambda: service
    try:
        response = api_client.post(
            "/api/v1/auth/onboarding",
            json={
                "history_mode": "new",
                "language": "ru",
                "accepted_rules": True,
            },
        )
    finally:
        app.dependency_overrides.pop(get_account_onboarding_service, None)

    assert response.status_code == 200
    assert service.calls == 1
    assert service.commit_values == [False]
    assert response.json()["onboarding_required"] is False


def test_onboarding_rejects_inactive_authenticated_user(
    db,
    api_client,
):
    user = _create_arena_user(db, is_active=False)
    _authenticate_client(db, api_client, user)

    response = api_client.post(
        "/api/v1/auth/onboarding",
        json={
            "history_mode": "new",
            "language": "ru",
            "accepted_rules": True,
        },
    )

    assert response.status_code == 401


def test_repeated_onboarding_returns_safe_validation_error(
    db,
    api_client,
):
    user = _create_arena_user(
        db,
        onboarding_completed_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )
    _authenticate_client(db, api_client, user)

    response = api_client.post(
        "/api/v1/auth/onboarding",
        json={
            "history_mode": "full",
            "language": "en",
            "accepted_rules": True,
            "password": "replacement-password",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": {"code": "onboarding_invalid"}}
    assert "replacement-password" not in response.text


@pytest.mark.parametrize(
    "password",
    [
        "tiny",
        "sensitive-overlong-password-" + "x" * 129,
    ],
)
def test_onboarding_422_never_reflects_rejected_password(
    db,
    api_client,
    password,
):
    user = _create_arena_user(db)
    _authenticate_client(db, api_client, user)

    response = api_client.post(
        "/api/v1/auth/onboarding",
        json={
            "history_mode": "new",
            "language": "ru",
            "accepted_rules": True,
            "password": password,
        },
    )

    assert response.status_code == 422
    assert password not in response.text


def test_password_login_uses_case_insensitive_current_verified_nickname(
    db,
    api_client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "SESSION_TTL_SECONDS", 8113)
    password = "correct-local-password"
    user = _create_arena_user(
        db,
        current_nickname="CurrentArenaNick",
        username="private-internal-name",
        hashed_password=get_password_hash(password),
        onboarding_completed_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )

    response = api_client.post(
        "/api/v1/auth/password-login",
        json={"nickname": "currentarenanick", "password": password},
    )

    assert response.status_code == 200
    cookie = _cookie_headers(response)[0]
    assert response.json()["id"] == user.id
    assert response.json()["onboarding_required"] is False
    assert db.query(UserSession).count() == 1
    assert cookie.startswith(settings.SESSION_COOKIE_NAME.lower() + "=")
    assert f"max-age={settings.SESSION_TTL_SECONDS}" in cookie
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie
    session = db.query(UserSession).one()
    assert session.token_hash not in response.text
    assert password not in response.text


def test_password_login_uses_persisted_unicode_canonical_nickname(
    db,
    api_client,
):
    password = "unicode-local-password"
    user = _create_arena_user(
        db,
        current_nickname="ИгрокStraße",
        username="unicode-internal-name",
        hashed_password=get_password_hash(password),
    )

    response = api_client.post(
        "/api/v1/auth/password-login",
        json={"nickname": "иГРОКSTRASSE", "password": password},
    )

    assert response.status_code == 200
    assert response.json()["id"] == user.id
    assert db.query(UserSession).count() == 1


def test_password_login_always_verifies_fixed_valid_dummy_hash(
    db,
    api_client,
    monkeypatch,
):
    password = "candidate-password"
    _create_arena_user(
        db,
        external_uuid="inactive-uuid",
        current_nickname="InactiveCandidate",
        username="inactive-candidate",
        is_active=False,
        hashed_password=get_password_hash("stored-password"),
    )
    _create_arena_user(
        db,
        external_uuid="no-password-uuid",
        current_nickname="NoPasswordCandidate",
        username="no-password-candidate",
        hashed_password=None,
    )
    calls = []

    def recording_verify(candidate, password_hash):
        calls.append((candidate, password_hash))
        return False

    monkeypatch.setattr(oauth_api, "verify_password", recording_verify)

    responses = [
        api_client.post(
            "/api/v1/auth/password-login",
            json={"nickname": nickname, "password": password},
        )
        for nickname in (
            "MissingCandidate",
            "InactiveCandidate",
            "NoPasswordCandidate",
        )
    ]

    assert [response.status_code for response in responses] == [401, 401, 401]
    assert len(calls) == 3
    assert {candidate for candidate, _password_hash in calls} == {password}
    dummy_hashes = {password_hash for _candidate, password_hash in calls}
    assert len(dummy_hashes) == 1
    dummy_hash = dummy_hashes.pop()
    assert dummy_hash.startswith("$bcrypt-sha256$")
    assert verify_password(password, dummy_hash) is False


@pytest.mark.parametrize(
    "login_name",
    ["FormerArenaNick", "private-internal-name"],
)
def test_password_login_rejects_aliases_and_internal_username(
    db,
    api_client,
    login_name,
):
    password = "correct-local-password"
    user = _create_arena_user(
        db,
        current_nickname="CurrentArenaNick",
        username="private-internal-name",
        hashed_password=get_password_hash(password),
    )
    identity = (
        db.query(ExternalPlayerIdentity).filter_by(user_id=user.id).one()
    )
    db.add(
        ExternalPlayerAlias(
            identity_id=identity.id,
            nickname="FormerArenaNick",
        )
    )
    db.commit()

    response = api_client.post(
        "/api/v1/auth/password-login",
        json={"nickname": login_name, "password": password},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "invalid_credentials"}}
    assert db.query(UserSession).count() == 0


@pytest.mark.parametrize(
    "account_state",
    [
        "missing",
        "ambiguous",
        "inactive",
        "unclaimed",
        "unverified_identity",
        "no_password",
        "invalid_password",
    ],
)
def test_password_login_rejects_all_invalid_credentials_uniformly(
    db,
    api_client,
    account_state,
):
    nickname = "FallbackPlayer"
    supplied_password = "supplied-secret-password"
    stored_password = "stored-secret-password"
    if account_state != "missing":
        user = _create_arena_user(
            db,
            current_nickname=nickname,
            username=f"internal-{account_state}",
            is_active=account_state != "inactive",
            is_claimed=account_state != "unclaimed",
            hashed_password=(
                None
                if account_state == "no_password"
                else get_password_hash(stored_password)
            ),
        )
        if account_state == "unverified_identity":
            identity = (
                db.query(ExternalPlayerIdentity)
                .filter_by(user_id=user.id)
                .one()
            )
            identity.verification_status = "unverified"
            db.commit()
        if account_state == "ambiguous":
            _create_arena_user(
                db,
                external_uuid="second-arena-uuid",
                current_nickname=nickname.lower(),
                username="second-internal-user",
                hashed_password=get_password_hash(stored_password),
            )
    password = (
        stored_password
        if account_state not in {"missing", "invalid_password"}
        else supplied_password
    )

    response = api_client.post(
        "/api/v1/auth/password-login",
        json={"nickname": nickname, "password": password},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "invalid_credentials"}}
    assert db.query(UserSession).count() == 0
    event = (
        db.query(SecurityAuditEvent)
        .filter(SecurityAuditEvent.event_type == "password_login_failed")
        .one()
    )
    assert event.event_metadata == {"reason": "invalid_credentials"}
    assert nickname not in repr(event.event_metadata)
    assert password not in repr(event.event_metadata)


def test_logout_revokes_current_session_clears_cookie_and_is_idempotent(
    db,
    api_client,
):
    user = _create_arena_user(db)
    token = _authenticate_client(db, api_client, user)

    first = api_client.post("/api/v1/auth/logout")
    second = api_client.post("/api/v1/auth/logout")

    db.expire_all()
    user_session = db.query(UserSession).one()
    assert first.status_code == 204
    assert first.content == b""
    assert second.status_code == 204
    assert user_session.revoked_at is not None
    assert token not in first.text
    for response in (first, second):
        cookie = _cookie_headers(response)[0]
        assert cookie.startswith(settings.SESSION_COOKIE_NAME.lower() + "=")
        assert "max-age=0" in cookie
        assert "httponly" in cookie
        assert "secure" in cookie
        assert "samesite=lax" in cookie
        assert "path=/" in cookie


def test_logout_without_valid_session_still_clears_cookie(api_client):
    api_client.cookies.set(
        settings.SESSION_COOKIE_NAME,
        "unknown-session-token",
        domain="testserver.local",
        path="/",
    )

    response = api_client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert any("max-age=0" in value for value in _cookie_headers(response))


class FailingRevokeSessionService:
    def revoke(self, db, token):
        db.add(User(username="must-be-rolled-back"))
        raise RuntimeError("database failure")


def test_logout_returns_503_and_clears_cookie_when_revoke_raises(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_session_service] = (
        lambda: FailingRevokeSessionService()
    )
    try:
        with TestClient(
            app,
            base_url="https://testserver",
            raise_server_exceptions=False,
        ) as client:
            client.cookies.set(
                settings.SESSION_COOKIE_NAME,
                "failing-revoke-token",
                domain="testserver.local",
                path="/",
            )
            response = client.post("/api/v1/auth/logout")
    finally:
        app.dependency_overrides.pop(get_session_service, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "logout_failed"}}
    assert "database failure" not in response.text
    assert any("max-age=0" in value for value in _cookie_headers(response))
    assert len(db.new) == 0


def test_revoke_all_revokes_every_user_session_including_current(
    db,
    api_client,
):
    user = _create_arena_user(db)
    current = SessionService().issue(db, user)
    SessionService().issue(db, user)
    api_client.cookies.set(
        settings.SESSION_COOKIE_NAME,
        current.token,
        domain="testserver.local",
        path="/",
    )

    response = api_client.post("/api/v1/auth/sessions/revoke-all")

    db.expire_all()
    sessions = db.query(UserSession).all()
    assert response.status_code == 200
    assert response.json() == {"revoked_count": 2}
    assert len(sessions) == 2
    assert all(
        user_session.revoked_at is not None for user_session in sessions
    )
    assert current.token not in response.text
    assert any("max-age=0" in value for value in _cookie_headers(response))


def test_revoke_all_requires_current_active_session(api_client):
    response = api_client.post("/api/v1/auth/sessions/revoke-all")

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "invalid_session"}}
