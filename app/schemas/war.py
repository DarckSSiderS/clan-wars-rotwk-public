from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime

class TerritoryBase(BaseModel):
    name: str
    region: str
    description: Optional[str] = None
    svg_path_data: str
    resource_wealth: int = 0
    strategic_value: float = 0
    population: int = 0
    fortifications: int = 0
    trade_routes: List[str] = Field(default_factory=list)
    special_resources: List[str] = Field(default_factory=list)
    climate: str = "temperate"
    terrain: str = "plains"
    status: str = "neutral"

class TerritoryCreate(TerritoryBase):
    pass

class TerritoryUpdate(BaseModel):
    name: Optional[str] = None
    region: Optional[str] = None
    description: Optional[str] = None
    svg_path_data: Optional[str] = None
    owner_clan_id: Optional[int] = None
    resource_wealth: Optional[int] = None
    strategic_value: Optional[float] = None
    population: Optional[int] = None
    fortifications: Optional[int] = None
    trade_routes: Optional[List[str]] = None
    special_resources: Optional[List[str]] = None
    climate: Optional[str] = None
    terrain: Optional[str] = None
    status: Optional[str] = None

class Territory(TerritoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_clan_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class ClanWarBase(BaseModel):
    territory_id: int
    source_territory_id: Optional[int] = None
    attacking_clan_id: Optional[int] = None
    defending_clan_id: Optional[int] = None
    war_type: Optional[str] = None
    required_wins: Optional[int] = None

class ClanWarCreate(ClanWarBase):
    squad_member_ids: List[int] = Field(min_length=1)
    warlord_user_id: int = Field(ge=1)
    expected_rule_version: int = Field(ge=1)

class ClanWar(ClanWarBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attacking_clan_id: Optional[int] = None
    war_type: str
    status: str
    required_wins: int
    started_at: datetime
    ends_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    winner_clan_id: Optional[int] = None
    attack_route: str = "land"
    attacker_power: int = 0
    defender_power: int = 0
    influence_cost: int = 0
    attacker_patch: str = "all"
    defender_patch: Optional[str] = None
    scoring_version: str = "elo_team_v2"
    campaign_rule_set_id: Optional[int] = None
    rules_snapshot: Optional[dict] = None

class ClanWarParticipantBase(BaseModel):
    war_id: int
    clan_id: int
    user_id: int
    wins: int = 0
    losses: int = 0
    is_active: bool = True

class ClanWarParticipantCreate(ClanWarParticipantBase):
    pass

class ClanWarParticipant(ClanWarParticipantBase):
    model_config = ConfigDict(from_attributes=True)

    id: int

class ClanWarScore(BaseModel):
    clan_id: int
    clan_name: str
    wins: int = 0
    losses: int = 0
    matches: int = 0
    points: float = 0
    manual_points: float = 0
    base_points: float = 0
    power_bonus_points: float = 0
    relic_bonus_points: float = 0
    team_bonus_points: float = 0
    legacy_points: float = 0
    win_rate: float = 0
    active_participants: int = 0


class WarGroupMember(BaseModel):
    user_id: int
    username: str
    display_nickname: str
    snapshot_nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    membership_started_at: Optional[datetime] = None
    membership_ended_at: Optional[datetime] = None
    assigned_at: Optional[datetime] = None
    status_code: str
    matches: int = 0
    wins: int = 0
    losses: int = 0
    points: float = 0


class WarSideGroup(BaseModel):
    clan_id: int
    clan_name: str
    clan_avatar_url: Optional[str] = None
    clan_map_color: Optional[str] = None
    role: str
    scope: str
    defense_rule: str
    member_count: int
    members: List[WarGroupMember]

class ClanWarDetails(BaseModel):
    score_adjustments: list[dict] = Field(default_factory=list)
    id: int
    territory_id: int
    territory_name: str
    attacking_clan_id: Optional[int] = None
    attacking_clan_name: str
    attacking_clan_avatar_url: Optional[str] = None
    attacking_clan_map_emblem_url: Optional[str] = None
    attacking_clan_map_color: Optional[str] = None
    defending_clan_id: Optional[int] = None
    defending_clan_name: Optional[str] = None
    defending_clan_avatar_url: Optional[str] = None
    defending_clan_map_emblem_url: Optional[str] = None
    defending_clan_map_color: Optional[str] = None
    winner_clan_id: Optional[int] = None
    winner_clan_name: Optional[str] = None
    war_type: str
    status: str
    required_wins: int
    started_at: datetime
    ends_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    clan_scores: List[ClanWarScore] = Field(default_factory=list)
    match_breakdown: List[dict] = Field(default_factory=list)
    tracked_matches: int = 0
    rejected_matches: int = 0
    progress_percent: int = 0
    source_territory_id: Optional[int] = None
    attacker_power: int = 0
    defender_power: int = 0
    influence_cost: int = 0
    attack_route: str = "land"
    days_remaining: Optional[int] = None
    scoring_rules: Optional[dict] = None
    attacker_patch: str = "all"
    defender_patch: Optional[str] = None
    scoring_version: str = "elo_team_v2"
    deployment_tracking: bool = False
    side_groups: List[WarSideGroup] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
