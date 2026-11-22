import math

import pytest
from pydantic import ValidationError

from app.config import Settings


def make_settings(**overrides):
    return Settings(_env_file=None, **overrides)


def test_oauth_is_disabled_with_safe_defaults(monkeypatch):
    for name in (
        "BFME_OAUTH_ENABLED",
        "BFME_OAUTH_CLIENT_ID",
        "BFME_OAUTH_CLIENT_SECRET",
        "BFME_OAUTH_REDIRECT_URI",
        "BFME_OAUTH_AUTHORIZE_URL",
        "BFME_OAUTH_TOKEN_URL",
        "BFME_OAUTH_IDENTITY_URL",
        "BFME_OAUTH_HTTP_TIMEOUT_SECONDS",
        "BFME_OAUTH_STATE_TTL_SECONDS",
        "SESSION_TTL_SECONDS",
        "BFME_PRIMARY_ADMIN_UUID",
        "SESSION_COOKIE_NAME",
        "OAUTH_FLOW_COOKIE_NAME",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = make_settings()

    assert settings.BFME_OAUTH_ENABLED is False
    assert settings.BFME_OAUTH_CLIENT_ID == ""
    assert settings.BFME_OAUTH_CLIENT_SECRET == ""
    assert settings.BFME_OAUTH_REDIRECT_URI == ""
    assert settings.BFME_OAUTH_AUTHORIZE_URL == "https://bfmeladder.com/oauth2/authorize"
    assert settings.BFME_OAUTH_TOKEN_URL == "https://bfmeladder.com/oauth2/token"
    assert settings.BFME_OAUTH_IDENTITY_URL == "https://bfmeladder.com/oauth2/userinfo"
    assert settings.BFME_OAUTH_HTTP_TIMEOUT_SECONDS == 10.0
    assert settings.BFME_OAUTH_STATE_TTL_SECONDS == 600
    assert settings.SESSION_TTL_SECONDS == 604800
    assert settings.BFME_PRIMARY_ADMIN_UUID == ""
    assert settings.SESSION_COOKIE_NAME == "rotwk_session"
    assert settings.OAUTH_FLOW_COOKIE_NAME == "rotwk_oauth_flow"


def test_enabled_oauth_accepts_complete_https_configuration():
    settings = make_settings(
        BFME_OAUTH_ENABLED=True,
        BFME_OAUTH_CLIENT_ID="client-id",
        BFME_OAUTH_CLIENT_SECRET="client-secret",
        BFME_OAUTH_REDIRECT_URI="https://example.com/auth/callback",
        BFME_PRIMARY_ADMIN_UUID="admin-uuid",
    )

    assert settings.BFME_OAUTH_ENABLED is True


@pytest.mark.parametrize(
    "field",
    [
        "BFME_OAUTH_CLIENT_ID",
        "BFME_OAUTH_CLIENT_SECRET",
        "BFME_OAUTH_REDIRECT_URI",
        "BFME_PRIMARY_ADMIN_UUID",
    ],
)
def test_enabled_oauth_rejects_missing_required_values(field):
    values = {
        "BFME_OAUTH_ENABLED": True,
        "BFME_OAUTH_CLIENT_ID": "client-id",
        "BFME_OAUTH_CLIENT_SECRET": "client-secret",
        "BFME_OAUTH_REDIRECT_URI": "https://example.com/auth/callback",
        "BFME_PRIMARY_ADMIN_UUID": "admin-uuid",
    }
    values[field] = ""

    with pytest.raises(ValidationError) as error:
        make_settings(**values)

    assert field in str(error.value)


def test_enabled_oauth_rejects_insecure_public_callback():
    with pytest.raises(ValidationError, match="HTTPS"):
        make_settings(
            BFME_OAUTH_ENABLED=True,
            BFME_OAUTH_CLIENT_ID="client-id",
            BFME_OAUTH_CLIENT_SECRET="client-secret",
            BFME_OAUTH_REDIRECT_URI="http://example.com/auth/callback",
            BFME_PRIMARY_ADMIN_UUID="admin-uuid",
        )


def test_enabled_oauth_allows_http_localhost_callback():
    settings = make_settings(
        BFME_OAUTH_ENABLED=True,
        BFME_OAUTH_CLIENT_ID="client-id",
        BFME_OAUTH_CLIENT_SECRET="client-secret",
        BFME_OAUTH_REDIRECT_URI="http://localhost:8000/auth/callback",
        BFME_PRIMARY_ADMIN_UUID="admin-uuid",
    )

    assert settings.BFME_OAUTH_REDIRECT_URI.startswith("http://localhost")


@pytest.mark.parametrize("callback", ["http://127.0.0.1/auth/callback", "http://[::1]/auth/callback"])
def test_enabled_oauth_rejects_http_ip_callbacks(callback):
    with pytest.raises(ValidationError, match="HTTPS"):
        make_settings(
            BFME_OAUTH_ENABLED=True,
            BFME_OAUTH_CLIENT_ID="client-id",
            BFME_OAUTH_CLIENT_SECRET="client-secret",
            BFME_OAUTH_REDIRECT_URI=callback,
            BFME_PRIMARY_ADMIN_UUID="admin-uuid",
        )


def test_enabled_oauth_callback_requires_authority():
    with pytest.raises(ValidationError, match="hostname"):
        make_settings(
            BFME_OAUTH_ENABLED=True,
            BFME_OAUTH_CLIENT_ID="client-id",
            BFME_OAUTH_CLIENT_SECRET="client-secret",
            BFME_OAUTH_REDIRECT_URI="https:callback",
            BFME_PRIMARY_ADMIN_UUID="admin-uuid",
        )


@pytest.mark.parametrize(
    "field",
    ["BFME_OAUTH_AUTHORIZE_URL", "BFME_OAUTH_TOKEN_URL", "BFME_OAUTH_IDENTITY_URL"],
)
def test_oauth_endpoint_urls_must_use_https(field):
    with pytest.raises(ValidationError, match="HTTPS"):
        make_settings(**{field: "http://example.com/oauth"})


@pytest.mark.parametrize(
    "field",
    ["BFME_OAUTH_AUTHORIZE_URL", "BFME_OAUTH_TOKEN_URL", "BFME_OAUTH_IDENTITY_URL"],
)
def test_oauth_endpoint_urls_require_authority(field):
    with pytest.raises(ValidationError, match="hostname"):
        make_settings(**{field: "https:oauth"})


@pytest.mark.parametrize(
    "field",
    [
        "BFME_OAUTH_HTTP_TIMEOUT_SECONDS",
        "BFME_OAUTH_STATE_TTL_SECONDS",
        "SESSION_TTL_SECONDS",
    ],
)
def test_oauth_timeouts_and_ttls_must_be_positive(field):
    with pytest.raises(ValidationError):
        make_settings(**{field: 0})


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_oauth_http_timeout_must_be_finite(value):
    with pytest.raises(ValidationError):
        make_settings(BFME_OAUTH_HTTP_TIMEOUT_SECONDS=value)


def test_redis_configuration_accepts_local_redis_url():
    settings = make_settings(
        REDIS_URL="redis://127.0.0.1:6379/0",
        REALTIME_REDIS_CHANNEL="clanwar:test:realtime",
    )

    assert settings.REDIS_URL == "redis://127.0.0.1:6379/0"
    assert settings.REALTIME_REDIS_CHANNEL == "clanwar:test:realtime"


@pytest.mark.parametrize("value", ["http://127.0.0.1:6379", "redis:local", "localhost:6379"])
def test_redis_configuration_rejects_invalid_urls(value):
    with pytest.raises(ValidationError, match="redis"):
        make_settings(REDIS_URL=value)


def test_redis_channel_must_not_be_empty():
    with pytest.raises(ValidationError, match="REALTIME_REDIS_CHANNEL"):
        make_settings(REALTIME_REDIS_CHANNEL="   ")


def production_settings(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "DEBUG": False,
        "SECRET_KEY": "production-secret-value-that-is-long-enough",
        "CORS_ORIGINS": ["https://bfmecw.online"],
        "BOOTSTRAP_TEST_ADMIN_ENABLED": False,
        "DATABASE_URL": "postgresql://clanwar@127.0.0.1/clanwar",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "PASSWORD_RECOVERY_SITE_URL": "https://bfmecw.online",
    }
    values.update(overrides)
    return make_settings(**values)


def test_production_configuration_accepts_safe_explicit_values():
    settings = production_settings()

    assert settings.ENVIRONMENT == "production"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"DEBUG": True}, "DEBUG"),
        ({"SECRET_KEY": "your-secret-key-here"}, "SECRET_KEY"),
        ({"CORS_ORIGINS": ["*"]}, "CORS_ORIGINS"),
        ({"BOOTSTRAP_TEST_ADMIN_ENABLED": True}, "BOOTSTRAP_TEST_ADMIN_ENABLED"),
        ({"DATABASE_URL": "sqlite:///clanwar.db"}, "PostgreSQL"),
        ({"REDIS_URL": ""}, "REDIS_URL"),
        ({"PASSWORD_RECOVERY_SITE_URL": "http://localhost:3000"}, "PASSWORD_RECOVERY_SITE_URL"),
    ],
)
def test_production_configuration_rejects_unsafe_values(override, message):
    with pytest.raises(ValidationError, match=message):
        production_settings(**override)
