from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal, Optional, List
from datetime import datetime
from app.core.clan_colors import CLAN_MAP_COLORS

class ClanBase(BaseModel):
    name: str
    motto: Optional[str] = Field(default=None, max_length=160)
    description: Optional[str] = None
    preferred_patch: str = "all"
    map_color: Optional[str] = None
    is_recruiting: bool = True

    @field_validator("preferred_patch")
    @classmethod
    def validate_preferred_patch(cls, value: str) -> str:
        if value not in {"patch_202", "ennorath", "all"}:
            raise ValueError("Допустимые патчи: Patch 2.02, Ennorath или все")
        return value

    @field_validator("map_color")
    @classmethod
    def validate_map_color(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        normalized = value.strip().upper()
        if (
            len(normalized) != 7
            or not normalized.startswith("#")
            or any(symbol not in "0123456789ABCDEF" for symbol in normalized[1:])
        ):
            raise ValueError("Цвет клана должен быть записан в формате #RRGGBB")
        return normalized

class ClanCreate(ClanBase):
    @field_validator("map_color")
    @classmethod
    def validate_current_map_color(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in CLAN_MAP_COLORS:
            raise ValueError("Выберите цвет из палитры клана")
        return value

class ClanUpdate(BaseModel):
    name: Optional[str] = None
    motto: Optional[str] = Field(default=None, max_length=160)
    description: Optional[str] = None
    preferred_patch: Optional[str] = None
    map_color: Optional[str] = None
    is_recruiting: Optional[bool] = None

    @field_validator("preferred_patch")
    @classmethod
    def validate_preferred_patch(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in {"patch_202", "ennorath", "all"}:
            raise ValueError("Допустимые патчи: Patch 2.02, Ennorath или все")
        return value

    @field_validator("map_color")
    @classmethod
    def validate_map_color(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().upper()
        if normalized not in CLAN_MAP_COLORS:
            raise ValueError("Выберите цвет из палитры клана")
        return normalized


class ClanMapColorGroup(BaseModel):
    key: str
    colors: List[str]


class ClanMapColorBlock(BaseModel):
    color: str
    reason: Literal["occupied"]


class ClanMapColorState(BaseModel):
    groups: List[ClanMapColorGroup]
    blocked_colors: List[ClanMapColorBlock]
    season_started: bool
    can_change_existing: bool

class Clan(ClanBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    leader_id: Optional[int] = None
    avatar_url: Optional[str] = None
    map_emblem_url: Optional[str] = None
    map_color: Optional[str] = None
    map_color_change_used: bool = False
    level: int
    experience: int
    max_members: int
    resources: int = 0
    base_influence: int = 100
    territory_points: int = 0
    gold_income_remainder: float = 0
    gold: int = 0
    iron: int = 0
    wood: int = 0
    food: int = 0
    mithril: int = 0
    is_admin_clan: bool = False
    is_recruiting: bool = True
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    preferred_patch: str = "all"
    next_attack_at: Optional[datetime] = None
    created_at: datetime

    @field_validator("is_recruiting", mode="before")
    @classmethod
    def default_recruiting_state(cls, value: Optional[bool]) -> bool:
        return True if value is None else value

    @field_validator("is_deleted", mode="before")
    @classmethod
    def default_deleted_state(cls, value: Optional[bool]) -> bool:
        return False if value is None else value

class ClanWithMemberCount(Clan):
    member_count: int
    territory_count: int = 0

class ClanMemberBase(BaseModel):
    rank: str = "Салага"


class ClanMemberRoleUpdate(BaseModel):
    role: Literal["Торговец", "Воин", "Салага"]

class ClanMemberCreate(ClanMemberBase):
    user_id: int
    clan_id: int

class ClanMember(ClanMemberBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    clan_id: int
    joined_at: datetime
    is_trader: bool = False
    is_warlord: bool = False

class ClanMemberWithUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    clan_id: int
    rank: str
    joined_at: datetime
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    is_trader: bool = False
    is_warlord: bool = False
    warlord_busy: bool = False

class ClanInviteBase(BaseModel):
    clan_id: int
    invitee_id: int

class ClanInviteCreate(BaseModel):
    invitee_id: int

class ClanInvite(ClanInviteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    inviter_id: int
    message: Optional[str] = None
    status: str
    created_at: datetime

class ClanInviteWithDetails(ClanInvite):
    clan_name: str
    inviter_username: str
    invitee_username: str

class ClanApplicationBase(BaseModel):
    message: Optional[str] = None

class ClanApplicationCreate(ClanApplicationBase):
    pass

class ClanApplicationUpdate(BaseModel):
    status: str

class ClanApplication(ClanApplicationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clan_id: int
    user_id: int
    status: str
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[int] = None

class ClanApplicationWithDetails(ClanApplication):
    clan_name: str
    user_username: str
    reviewer_username: Optional[str] = None
    user: dict  # Добавляем поле user для фронтенда

class KickMemberRequest(BaseModel):
    user_id: int

class TransferLeadershipRequest(BaseModel):
    user_id: int


class ClanLevelThresholdResponse(BaseModel):
    level: int
    attack_capacity: int
    active_members: int
    territories: int
    influence: int


class ClanLevelStatusResponse(BaseModel):
    level: int
    attack_capacity: int
    active_member_count: int
    territory_count: int
    influence: int
    next_level: Optional[ClanLevelThresholdResponse] = None
    missing: dict[str, int]


class AttackPointRecoveryResponse(BaseModel):
    spend_id: int
    recover_at: datetime
    war_id: Optional[int] = None


class ClanAttackPointStatusResponse(BaseModel):
    capacity: int
    available: int
    recovering: int
    blocked: int
    next_attack_at: Optional[datetime] = None
    recoveries: List[AttackPointRecoveryResponse]


class DeploymentCandidateResponse(BaseModel):
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    nickname: str
    verified: bool
    activity_matches: int
    is_warlord: bool
    busy_in_attack: bool
    busy_war_id: Optional[int] = None


class ClanWarReadiness(BaseModel):
    clan_id: int
    level: ClanLevelStatusResponse
    attack_points: ClanAttackPointStatusResponse
    candidates: List[DeploymentCandidateResponse]
    minimum_squad_size: int
    warlord_limit: int
    warlord_count: int
    rule_version: int


class ClanMemberWarlordUpdate(BaseModel):
    is_warlord: bool


class MarketOfferCreate(BaseModel):
    creator_clan_id: int
    give_resource: Literal["gold", "iron", "wood", "food", "mithril"]
    give_amount: int = Field(gt=0, le=100000)
    receive_resource: Literal["gold", "iron", "wood", "food", "mithril"]
    receive_amount: int = Field(gt=0, le=100000)
    expires_in_days: int = Field(default=7, ge=1, le=14)

    @field_validator("receive_resource")
    @classmethod
    def validate_distinct_resources(cls, value: str, info):
        if value == info.data.get("give_resource"):
            raise ValueError("Для обмена выберите разные ресурсы")
        return value


class MarketOfferAccept(BaseModel):
    accepter_clan_id: int
