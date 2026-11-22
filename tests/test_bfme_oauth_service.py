import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import aiohttp
import pytest

from app.services.bfme_oauth_service import (
    ArenaIdentity,
    ArenaOAuthRejected,
    ArenaOAuthUnavailable,
    BfmeOAuthService,
)


@dataclass
class RecordedRequest:
    url: str
    data: dict | None = None
    headers: dict | None = None


class FakeResponse:
    def __init__(self, status=200, payload=None, json_error=None):
        self.status = status
        self.payload = payload
        self.json_error = json_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def json(self):
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class FakeSession:
    def __init__(self, post_results=(), get_results=()):
        self.post_results = list(post_results)
        self.get_results = list(get_results)
        self.posts = []
        self.gets = []
        self.close_calls = 0

    def post(self, url, *, data):
        self.posts.append(RecordedRequest(url=url, data=data))
        return self._next(self.post_results)

    def get(self, url, *, headers):
        self.gets.append(RecordedRequest(url=url, headers=headers))
        return self._next(self.get_results)

    async def close(self):
        self.close_calls += 1

    @staticmethod
    def _next(results):
        result = results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


@pytest.fixture
def oauth_settings():
    return SimpleNamespace(
        BFME_OAUTH_AUTHORIZE_URL="https://arena.example/oauth/authorize",
        BFME_OAUTH_TOKEN_URL="https://arena.example/oauth/token",
        BFME_OAUTH_IDENTITY_URL="https://arena.example/oauth/identity",
        BFME_OAUTH_CLIENT_ID="arena-client",
        BFME_OAUTH_CLIENT_SECRET="client-secret-private",
        BFME_OAUTH_REDIRECT_URI="https://clan.example/auth/arena/callback",
        BFME_OAUTH_HTTP_TIMEOUT_SECONDS=4.5,
    )


def make_service(oauth_settings, fake_session):
    return BfmeOAuthService(oauth_settings, session_factory=lambda: fake_session)


def valid_token_payload(**overrides):
    payload = {
        "access_token": "access-private",
        "token_type": "bEaReR",
        "expires_in": 3600,
        "scope": "profile identity",
    }
    payload.update(overrides)
    return payload


def valid_identity_payload(**overrides):
    payload = {"uuid": "uuid-1", "displayName": "Bull"}
    payload.update(overrides)
    return payload


def test_build_authorize_url_encodes_exact_query(oauth_settings):
    service = BfmeOAuthService(oauth_settings)

    url = service.build_authorize_url("state with space")

    assert url == (
        "https://arena.example/oauth/authorize?client_id=arena-client&"
        "redirect_uri=https%3A%2F%2Fclan.example%2Fauth%2Farena%2Fcallback&"
        "state=state+with+space"
    )


@pytest.mark.asyncio
async def test_exchange_code_posts_exact_form_and_returns_access_token(oauth_settings):
    fake_session = FakeSession(post_results=[FakeResponse(payload=valid_token_payload())])
    service = make_service(oauth_settings, fake_session)

    token = await service.exchange_code("one-time-code-private")

    assert token == "access-private"
    assert fake_session.posts == [
        RecordedRequest(
            url="https://arena.example/oauth/token",
            data={
                "code": "one-time-code-private",
                "redirect_url": "https://clan.example/auth/arena/callback",
                "redirect_uri": "https://clan.example/auth/arena/callback",
                "client_id": "arena-client",
                "client_secret": "client-secret-private",
                "grant_type": "authorization_code",
            },
        )
    ]
    assert fake_session.close_calls == 0


@pytest.mark.asyncio
async def test_fetch_identity_sends_exact_headers_and_trims_display_name(oauth_settings):
    fake_session = FakeSession(
        get_results=[FakeResponse(payload=valid_identity_payload(displayName="  Bull  "))]
    )
    service = make_service(oauth_settings, fake_session)

    identity = await service.fetch_identity("access-private")

    assert identity == ArenaIdentity(uuid="uuid-1", display_name="Bull")
    assert fake_session.gets == [
        RecordedRequest(
            url="https://arena.example/oauth/identity",
            headers={"Authorization": "Bearer access-private", "Accept": "application/json"},
        )
    ]
    assert fake_session.close_calls == 0


@pytest.mark.parametrize("status", [400, 401, 403])
@pytest.mark.asyncio
async def test_exchange_code_classifies_rejected_responses_without_secrets(oauth_settings, status):
    fake_session = FakeSession(post_results=[FakeResponse(status=status, payload={"error": "denied"})])
    service = make_service(oauth_settings, fake_session)

    with pytest.raises(ArenaOAuthRejected) as error:
        await service.exchange_code("one-time-code-private")

    message = str(error.value)
    assert error.value.stage == "token"
    assert error.value.status == status
    assert error.value.provider_error == "other"
    assert "one-time-code-private" not in message
    assert "client-secret-private" not in message
    assert "denied" not in message


@pytest.mark.asyncio
async def test_identity_rejection_records_only_stage_and_status(oauth_settings):
    fake_session = FakeSession(get_results=[FakeResponse(status=401)])
    service = make_service(oauth_settings, fake_session)

    with pytest.raises(ArenaOAuthRejected) as error:
        await service.fetch_identity("access-private")

    assert error.value.stage == "identity"
    assert error.value.status == 401
    assert error.value.provider_error is None
    assert "access-private" not in str(error.value)


@pytest.mark.asyncio
async def test_rejection_exposes_only_allowlisted_provider_error(oauth_settings):
    fake_session = FakeSession(
        post_results=[
            FakeResponse(
                status=400,
                payload={
                    "error": "invalid_grant",
                    "error_description": "authorization-code-secret",
                },
            )
        ]
    )
    service = make_service(oauth_settings, fake_session)

    with pytest.raises(ArenaOAuthRejected) as error:
        await service.exchange_code("authorization-code-secret")

    assert error.value.provider_error == "invalid_grant"
    assert "authorization-code-secret" not in str(error.value)


@pytest.mark.parametrize(
    "request_kind, failure",
    [
        ("token", asyncio.TimeoutError()),
        ("identity", aiohttp.ClientConnectionError("network-private")),
    ],
)
@pytest.mark.asyncio
async def test_external_timeout_and_connection_failures_are_unavailable(
    oauth_settings, request_kind, failure
):
    fake_session = FakeSession(
        post_results=[failure] if request_kind == "token" else [],
        get_results=[failure] if request_kind == "identity" else [],
    )
    service = make_service(oauth_settings, fake_session)

    with pytest.raises(ArenaOAuthUnavailable) as error:
        if request_kind == "token":
            await service.exchange_code("one-time-code-private")
        else:
            await service.fetch_identity("access-private")

    message = str(error.value)
    assert "one-time-code-private" not in message
    assert "client-secret-private" not in message
    assert "access-private" not in message
    assert "network-private" not in message


@pytest.mark.parametrize("request_kind", ["token", "identity"])
@pytest.mark.asyncio
async def test_server_error_responses_are_unavailable(oauth_settings, request_kind):
    fake_session = FakeSession(
        post_results=[FakeResponse(status=503, payload={"error": "private-body"})]
        if request_kind == "token"
        else [],
        get_results=[FakeResponse(status=503, payload={"error": "private-body"})]
        if request_kind == "identity"
        else [],
    )
    service = make_service(oauth_settings, fake_session)

    with pytest.raises(ArenaOAuthUnavailable) as error:
        if request_kind == "token":
            await service.exchange_code("one-time-code-private")
        else:
            await service.fetch_identity("access-private")

    assert "private-body" not in str(error.value)


@pytest.mark.parametrize("request_kind", ["token", "identity"])
@pytest.mark.asyncio
async def test_invalid_json_is_unavailable(oauth_settings, request_kind):
    response = FakeResponse(json_error=ValueError("private-json"))
    fake_session = FakeSession(
        post_results=[response] if request_kind == "token" else [],
        get_results=[response] if request_kind == "identity" else [],
    )
    service = make_service(oauth_settings, fake_session)

    with pytest.raises(ArenaOAuthUnavailable) as error:
        if request_kind == "token":
            await service.exchange_code("one-time-code-private")
        else:
            await service.fetch_identity("access-private")

    assert "private-json" not in str(error.value)


@pytest.mark.parametrize(
    "payload",
    [
        {"token_type": "Bearer", "expires_in": 3600, "scope": "identity"},
        valid_token_payload(access_token="   "),
        valid_token_payload(access_token=7),
        valid_token_payload(token_type="Basic"),
        valid_token_payload(token_type=7),
        valid_token_payload(expires_in=0),
        valid_token_payload(expires_in=False),
        valid_token_payload(expires_in="3600"),
    ],
)
@pytest.mark.asyncio
async def test_malformed_token_fields_are_unavailable(oauth_settings, payload):
    fake_session = FakeSession(post_results=[FakeResponse(payload=payload)])
    service = make_service(oauth_settings, fake_session)

    with pytest.raises(ArenaOAuthUnavailable) as error:
        await service.exchange_code("one-time-code-private")

    assert "one-time-code-private" not in str(error.value)
    assert "client-secret-private" not in str(error.value)


@pytest.mark.asyncio
async def test_token_response_requires_identity_scope(oauth_settings):
    fake_session = FakeSession(post_results=[FakeResponse(payload=valid_token_payload(scope="profile"))])
    service = make_service(oauth_settings, fake_session)

    with pytest.raises(ArenaOAuthUnavailable):
        await service.exchange_code("one-time-code-private")


@pytest.mark.parametrize(
    "payload",
    [
        {"displayName": "Bull"},
        valid_identity_payload(uuid="   "),
        valid_identity_payload(uuid="u" * 81),
        {"uuid": "uuid-1"},
        valid_identity_payload(displayName="   "),
        valid_identity_payload(displayName="B" * 121),
        valid_identity_payload(displayName=7),
    ],
)
@pytest.mark.asyncio
async def test_missing_or_oversized_identity_fields_are_unavailable(oauth_settings, payload):
    fake_session = FakeSession(get_results=[FakeResponse(payload=payload)])
    service = make_service(oauth_settings, fake_session)

    with pytest.raises(ArenaOAuthUnavailable) as error:
        await service.fetch_identity("access-private")

    assert "access-private" not in str(error.value)
