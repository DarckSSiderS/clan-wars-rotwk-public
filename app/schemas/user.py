from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional, Dict, Any, Literal, List
from datetime import datetime
from app.schemas.role import UserRoleResponse

class UserBase(BaseModel):
    username: str
    email: Optional[EmailStr] = None

class UserCreate(UserBase):
    email: EmailStr
    password: str
    claim_existing_profile: bool = False
    language: str = "ru"  # По умолчанию русский
    allow_clan_invites: bool = True  # По умолчанию разрешены приглашения
    telegram_url: Optional[str] = None
    twitch_url: Optional[str] = None
    youtube_url: Optional[str] = None

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    language: Optional[str] = None
    allow_clan_invites: Optional[bool] = None
    telegram_url: Optional[str] = None
    twitch_url: Optional[str] = None
    youtube_url: Optional[str] = None

class BalanceUpdate(BaseModel):
    amount: int
    reason: str = Field(min_length=3, max_length=500)


class IdentityVerificationReview(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str = Field(min_length=3, max_length=500)


class PublicUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_active: bool
    is_claimed: bool = True
    level: int
    experience: int
    avatar_url: Optional[str] = None
    allow_clan_invites: bool
    telegram_url: Optional[str] = None
    twitch_url: Optional[str] = None
    youtube_url: Optional[str] = None
    role: Optional[UserRoleResponse] = None
    created_at: datetime
    player_statistics: Optional[Dict[str, Any]] = None
    external_identity_status: Optional[str] = None

class User(UserBase):
    model_config = ConfigDict(from_attributes=True)

    # В ответах сохраняем исторические технические адреса ladder-профилей.
    # Регистрация и редактирование по-прежнему используют строгий EmailStr.
    email: Optional[str] = None
    id: int
    display_name: Optional[str] = None
    is_active: bool
    is_claimed: bool = True
    balance: int
    level: int
    experience: int
    avatar_url: Optional[str] = None
    language: str
    allow_clan_invites: bool
    telegram_url: Optional[str] = None
    twitch_url: Optional[str] = None
    youtube_url: Optional[str] = None
    role: Optional[UserRoleResponse] = None
    created_at: datetime
    onboarding_completed_at: Optional[datetime] = None
    history_mode: Optional[Literal["new", "full"]] = None
    statistics_started_at: Optional[datetime] = None
    player_statistics: Optional[Dict[str, Any]] = None
    external_identity_status: Optional[str] = None
    is_admin_impersonation: bool = False
    impersonated_by_username: Optional[str] = None

class TerritoryContributionSummary(BaseModel):
    wars: int
    matches: int
    wins: int
    losses: int
    score: float
    territories_helped: int


class TerritoryContributionItem(BaseModel):
    territory_id: int
    territory_name: str
    wars: int
    matches: int
    wins: int
    losses: int
    score: float
    last_action_at: Optional[datetime] = None
    clan_id: Optional[int] = None
    clan_name: Optional[str] = None


class TerritoryContributionResponse(BaseModel):
    season_id: Optional[int] = None
    season_name: Optional[str] = None
    summary: TerritoryContributionSummary
    territories: List[TerritoryContributionItem]
