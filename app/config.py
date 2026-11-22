from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional
from datetime import datetime
import math
import os
from urllib.parse import urlsplit
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Основные настройки
    APP_NAME: str = "ClanWar API"
    APP_VERSION: str = "1.0.0"
    DISCORD_ENABLED: bool = False
    DISCORD_BOT_TOKEN: SecretStr = SecretStr("")
    DISCORD_APPLICATION_ID: int = 100000000000000001
    DISCORD_GUILD_ID: int = 0
    DISCORD_SITE_URL: str = "https://bfmecw.online"
    DISCORD_SYNC_SECONDS: int = Field(default=60, ge=30, le=3600)
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DEBUG: bool = False
    
    # База данных
    DATABASE_URL: str = "postgresql://clanwar_user:clanwar_password@localhost:5432/clanwar_db"
    
    # JWT настройки
    SECRET_KEY: str = "your-secret-key-here"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # Восстановление доступа. Секреты SMTP задаются только окружением.
    PASSWORD_RECOVERY_TTL_MINUTES: int = 30
    PASSWORD_RECOVERY_SITE_URL: str = "http://localhost:3000"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_USE_TLS: bool = True

    # Тестовый админ для локальных проверок
    DEFAULT_ADMIN_USERNAME: str = "clanwar"
    DEFAULT_ADMIN_PASSWORD: str = "admin"
    DEFAULT_ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_CLAN_USERNAME: str = "clanwar"
    ADMIN_CLAN_PASSWORD: str = "admin"
    ADMIN_CLAN_EMAIL: str = "clanwar@example.com"
    ADMIN_CLAN_NAME: str = "Совет Тол-Фаласа"
    BOOTSTRAP_TEST_ADMIN_ENABLED: bool = False
    
    # Настройки безопасности
    CORS_ORIGINS: list = ["*"]
    
    # Настройки файлов
    UPLOAD_DIR: str = "frontend/public/images"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_IMAGE_TYPES: list = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    
    # Настройки планировщика
    SCHEDULER_UPDATE_INTERVAL: int = 600
    WAR_REPLAY_GRACE_MINUTES: int = Field(default=5, ge=0, le=1440)
    WAR_MIN_MATCH_DURATION_EFFECTIVE_AT: datetime | None = None
    WAR_PREVIOUS_MIN_MATCH_DURATION_SECONDS: int = Field(default=120, ge=0)
    WORKER_ALERT_WEBHOOK_URL: str = ""
    WORKER_ALERT_TIMEOUT_SECONDS: float = 5.0
    ARENA_BACKFILL_JOBS_PER_CYCLE: int = 2
    ARENA_BACKFILL_MAX_PAGES: int = 1000
    ARENA_BACKFILL_RETRY_SECONDS: int = 60

    # Межпроцессная доставка WebSocket-событий. Пустое значение оставляет
    # локальный in-process транспорт для разработки и тестов.
    REDIS_URL: str = ""
    REALTIME_REDIS_CHANNEL: str = "clanwar:realtime:v1"
    REDIS_CONNECT_TIMEOUT_SECONDS: float = 2.0
    PRESENCE_REDIS_KEY: str = "clanwar:presence:v1"
    PRESENCE_TTL_SECONDS: int = 75
    ONLINE_REQUEST_COOLDOWN_SECONDS: int = 60

    BFME_OAUTH_ENABLED: bool = False
    BFME_OAUTH_CLIENT_ID: str = ""
    BFME_OAUTH_CLIENT_SECRET: str = ""
    BFME_OAUTH_REDIRECT_URI: str = ""
    BFME_OAUTH_AUTHORIZE_URL: str = "https://bfmeladder.com/oauth2/authorize"
    BFME_OAUTH_TOKEN_URL: str = "https://bfmeladder.com/oauth2/token"
    BFME_OAUTH_IDENTITY_URL: str = "https://bfmeladder.com/oauth2/userinfo"
    BFME_OAUTH_HTTP_TIMEOUT_SECONDS: float = 10.0
    BFME_OAUTH_STATE_TTL_SECONDS: int = 600
    SESSION_TTL_SECONDS: int = 604800
    SESSION_COOKIE_NAME: str = "rotwk_session"
    OAUTH_FLOW_COOKIE_NAME: str = "rotwk_oauth_flow"
    BFME_PRIMARY_ADMIN_UUID: str = ""

    @field_validator(
        "BFME_OAUTH_AUTHORIZE_URL",
        "BFME_OAUTH_TOKEN_URL",
        "BFME_OAUTH_IDENTITY_URL",
    )
    @classmethod
    def validate_oauth_endpoint_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https":
            raise ValueError("OAuth URL must use HTTPS")
        if parsed.hostname is None:
            raise ValueError("OAuth URL must include a hostname")
        return value

    @field_validator(
        "BFME_OAUTH_HTTP_TIMEOUT_SECONDS",
        "BFME_OAUTH_STATE_TTL_SECONDS",
        "SESSION_TTL_SECONDS",
        "REDIS_CONNECT_TIMEOUT_SECONDS",
        "PRESENCE_TTL_SECONDS",
        "ONLINE_REQUEST_COOLDOWN_SECONDS",
        "ARENA_BACKFILL_JOBS_PER_CYCLE",
        "ARENA_BACKFILL_MAX_PAGES",
        "ARENA_BACKFILL_RETRY_SECONDS",
    )
    @classmethod
    def validate_positive_duration(cls, value: float | int) -> float | int:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Timeouts and TTLs must be positive")
        return value

    @field_validator("REDIS_URL")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        if not value:
            return value
        parsed = urlsplit(value)
        if parsed.scheme not in {"redis", "rediss"} or parsed.hostname is None:
            raise ValueError("REDIS_URL must use redis:// or rediss://")
        return value

    @field_validator("REALTIME_REDIS_CHANNEL")
    @classmethod
    def validate_realtime_redis_channel(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("REALTIME_REDIS_CHANNEL must not be empty")
        return normalized

    @field_validator("PRESENCE_REDIS_KEY")
    @classmethod
    def validate_presence_redis_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("PRESENCE_REDIS_KEY must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_oauth_configuration(self):
        if not self.BFME_OAUTH_ENABLED:
            return self

        required_fields = (
            "BFME_OAUTH_CLIENT_ID",
            "BFME_OAUTH_CLIENT_SECRET",
            "BFME_OAUTH_REDIRECT_URI",
            "BFME_PRIMARY_ADMIN_UUID",
        )
        missing_fields = [field for field in required_fields if not getattr(self, field).strip()]
        if missing_fields:
            raise ValueError(f"Required OAuth fields are empty: {', '.join(missing_fields)}")

        callback = urlsplit(self.BFME_OAUTH_REDIRECT_URI)
        if callback.hostname is None:
            raise ValueError("OAuth callback must include a hostname")
        if callback.scheme != "https" and not (
            callback.scheme == "http" and callback.hostname == "localhost"
        ):
            raise ValueError("OAuth callback must use HTTPS, except for localhost")
        return self

    @model_validator(mode="after")
    def validate_production_configuration(self):
        if self.ENVIRONMENT != "production":
            return self

        errors = []
        if self.DEBUG:
            errors.append("DEBUG must be disabled")
        if self.SECRET_KEY in {"", "your-secret-key-here"} or len(self.SECRET_KEY) < 32:
            errors.append("SECRET_KEY must be a unique value of at least 32 characters")
        if "*" in self.CORS_ORIGINS or not self.CORS_ORIGINS:
            errors.append("CORS_ORIGINS must contain explicit production origins")
        if self.BOOTSTRAP_TEST_ADMIN_ENABLED:
            errors.append("BOOTSTRAP_TEST_ADMIN_ENABLED must be disabled")
        if urlsplit(self.DATABASE_URL).scheme not in {"postgres", "postgresql"}:
            errors.append("DATABASE_URL must use PostgreSQL")
        if not self.REDIS_URL:
            errors.append("REDIS_URL is required for multi-worker realtime")
        recovery_site = urlsplit(self.PASSWORD_RECOVERY_SITE_URL)
        if recovery_site.scheme != "https" or recovery_site.hostname is None:
            errors.append("PASSWORD_RECOVERY_SITE_URL must be a public HTTPS URL")

        if errors:
            raise ValueError("Unsafe production configuration: " + "; ".join(errors))
        return self

    # Настройки bfmeladder
    LADDER_BASE: str = "https://bfmeladder.com/replays"
    LADDER_API_BASE: str = "https://bfmeladder.com/api/replays"
    LADDER_REPLAY_BASE: str = "https://bfmeladder.com/replay"
    LADDER_API_SCAN_LIMIT: int = 500
    LADDER_API_PATCH_FILTER: str = ""
    LADDER_API_PATCH_WINDOW: int = 3
    REPLAY_STORAGE_DIR: str = "replays"
    REPLAY_MAX_FILE_SIZE: int = 50 * 1024 * 1024
    REPLAY_BACKFILL_PER_SYNC: int = 5
    MAP_PREVIEW_STORAGE_DIR: str = "map_previews"
    MAP_PREVIEW_MAX_FILE_SIZE: int = 8 * 1024 * 1024
    LADDER_GAME: str = "RotWK"
    LADDER_PATCH: str = "05a64473-c7f5-4fff-8e00-f30e06db9d96:1.9.7.7d"
    LADDER_GAMEMODE: str = "1 versus 1"
    LADDER_GAMEMODES: str = "1 versus 1,2 versus 2,3 versus 3,4 versus 4"
    LADDER_PUBLIC_API_BASE: str = "https://bfmeladder.com/api/public/replays"
    LADDER_PUBLIC_API_ENABLED: bool = False
    LADDER_PUBLIC_API_TOKEN: str = ""
    LADDER_PATCH_202_ARENA_ID: str = "2bd291d4-a624-481d-af9b-3a63ea9effa7"
    LADDER_ENNORATH_ARENA_ID: str = "8a0e14c4-3204-4973-96e3-62ba9dc8526b"
    # Старое имя оставлено для совместимости с существующими окружениями.
    LADDER_ARENA_ID: str = "2bd291d4-a624-481d-af9b-3a63ea9effa7"
    LADDER_SYNC_WINDOW_HOURS: int = 12
    LADDER_SYNC_OVERLAP_MINUTES: int = 15
    PROXY_URL: Optional[str] = None

    @field_validator("LADDER_GAMEMODES")
    @classmethod
    def validate_ladder_gamemodes(cls, value: str) -> str:
        supported = {
            "1 versus 1",
            "2 versus 2",
            "3 versus 3",
            "4 versus 4",
        }
        modes = []
        for raw_mode in value.split(","):
            mode = " ".join(raw_mode.split())
            if mode and mode not in modes:
                modes.append(mode)
        if not modes:
            raise ValueError("LADDER_GAMEMODES must contain at least one gamemode")
        unknown = sorted(set(modes) - supported)
        if unknown:
            raise ValueError(
                "Unsupported LADDER_GAMEMODES values: " + ", ".join(unknown)
            )
        return ",".join(modes)
    
settings = Settings()
