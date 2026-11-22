from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    computed_field,
    field_validator,
)

from app.schemas.role import UserRoleResponse


HistoryMode = Literal["new", "full"]
InterfaceLanguage = Literal["ru", "en", "de"]
REDACTED_SHORT_PASSWORD = "*" * 9
REDACTED_LONG_PASSWORD = "*" * 129


class OnboardingRequest(BaseModel):
    history_mode: HistoryMode
    language: InterfaceLanguage
    accepted_rules: StrictBool
    password: str | None = Field(default=None, min_length=10, max_length=128)

    model_config = ConfigDict(strict=True, hide_input_in_errors=True)

    @field_validator("accepted_rules")
    @classmethod
    def require_accepted_rules(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Необходимо принять правила проекта")
        return value

    @field_validator("password", mode="before")
    @classmethod
    def normalize_blank_password(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        if not value.strip():
            return None
        if len(value) < 10:
            return REDACTED_SHORT_PASSWORD
        if len(value) > 128:
            return REDACTED_LONG_PASSWORD
        return value


class PasswordLoginRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=128, repr=False)

    model_config = ConfigDict(strict=True, hide_input_in_errors=True)

    @field_validator("nickname", mode="before")
    @classmethod
    def normalize_nickname(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("password", mode="before")
    @classmethod
    def redact_overlong_password(cls, value: object) -> object:
        if isinstance(value, str) and len(value) > 128:
            return REDACTED_LONG_PASSWORD
        return value


class SessionUserSummary(BaseModel):
    id: int
    username: str
    display_name: str | None = None
    email: str | None = None
    is_active: bool
    is_claimed: bool = True
    balance: int
    level: int
    experience: int
    avatar_url: str | None = None
    language: InterfaceLanguage
    allow_clan_invites: bool
    telegram_url: str | None = None
    twitch_url: str | None = None
    youtube_url: str | None = None
    role: UserRoleResponse | None = None
    created_at: datetime
    onboarding_completed_at: datetime | None = None
    history_mode: HistoryMode | None = None
    statistics_started_at: datetime | None = None
    external_identity_status: str | None = None
    is_admin_impersonation: bool = False
    impersonated_by_username: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def onboarding_required(self) -> bool:
        return self.onboarding_completed_at is None


class RevokeAllResponse(BaseModel):
    revoked_count: int
