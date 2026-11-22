from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import List, Optional
from datetime import datetime


class TerritoryBase(BaseModel):
    name: str
    region: str
    description: Optional[str] = None
    svg_path_data: str
    resource_wealth: int = 0
    influence_value: int = 0
    required_influence: int = 30
    strategic_value: float = 0
    population: int = 0
    fortifications: int = 0
    trade_routes: List[str] = Field(default_factory=list)
    special_resources: List[str] = Field(default_factory=list)
    climate: str = 'temperate'
    terrain: str = 'plains'
    status: str = 'neutral'
    development_level: int = 0
    offense_level: int = 0
    adjacent_territory_ids: List[int] = Field(default_factory=list)
    resource_type: str = 'iron'
    resource_output: int = 1
    secondary_resource_type: Optional[str] = None
    is_playable: bool = True
    is_coastal: bool = False
    has_port: bool = False
    port_level: int = 0
    fleet_level: int = 0
    required_territories: int = 0
    stronghold_power: int = 0
    owned_since: Optional[datetime] = None
    last_weekly_payout_at: Optional[datetime] = None
    resource_income_ready_at: Optional[datetime] = None
    last_resource_payout_at: Optional[datetime] = None


class TerritoryCreate(TerritoryBase):
    pass


class TerritoryUpdate(BaseModel):
    name: Optional[str] = None
    region: Optional[str] = None
    description: Optional[str] = None
    svg_path_data: Optional[str] = None
    owner_clan_id: Optional[int] = None
    resource_wealth: Optional[int] = None
    influence_value: Optional[int] = None
    required_influence: Optional[int] = None
    strategic_value: Optional[float] = None
    population: Optional[int] = None
    fortifications: Optional[int] = None
    trade_routes: Optional[List[str]] = None
    special_resources: Optional[List[str]] = None
    climate: Optional[str] = None
    terrain: Optional[str] = None
    status: Optional[str] = None
    development_level: Optional[int] = None
    offense_level: Optional[int] = None
    adjacent_territory_ids: Optional[List[int]] = None
    resource_type: Optional[str] = None
    resource_output: Optional[int] = None
    secondary_resource_type: Optional[str] = None
    is_playable: Optional[bool] = None
    is_coastal: Optional[bool] = None
    has_port: Optional[bool] = None
    port_level: Optional[int] = None
    fleet_level: Optional[int] = None
    required_territories: Optional[int] = None
    stronghold_power: Optional[int] = None
    owned_since: Optional[datetime] = None
    last_weekly_payout_at: Optional[datetime] = None
    resource_income_ready_at: Optional[datetime] = None
    last_resource_payout_at: Optional[datetime] = None

    @field_validator(
        "resource_wealth",
        "influence_value",
        "required_influence",
        "population",
        "resource_output",
        "required_territories",
        "stronghold_power",
    )
    @classmethod
    def non_negative_values(cls, value):
        if value is not None and value < 0:
            raise ValueError("Значение не может быть отрицательным")
        return value

    @field_validator(
        "development_level",
        "fortifications",
        "offense_level",
        "port_level",
        "fleet_level",
    )
    @classmethod
    def upgrade_level_range(cls, value):
        if value is not None and not 0 <= value <= 10:
            raise ValueError("Уровень улучшения должен быть от 0 до 10")
        return value

    @field_validator("resource_type", "secondary_resource_type")
    @classmethod
    def valid_resource_type(cls, value):
        if value is not None and value not in {
            "gold",
            "iron",
            "wood",
            "food",
            "mithril",
        }:
            raise ValueError("Неизвестный ресурс территории")
        return value


class TerritoryResponse(TerritoryBase):
    model_config = ConfigDict(from_attributes=True)

    @field_validator('adjacent_territory_ids', 'trade_routes', 'special_resources', mode='before')
    @classmethod
    def empty_legacy_lists(cls, value):
        return [] if value is None else value

    id: int
    owner_clan_id: Optional[int] = None
    owner_clan_name: Optional[str] = None
    owner_clan_avatar_url: Optional[str] = None
    owner_clan_map_emblem_url: Optional[str] = None
    owner_clan_map_color: Optional[str] = None
    owner_clan_is_admin: bool = False
    attacking_clans: List[int] = Field(default_factory=list)
    defending_clans: List[int] = Field(default_factory=list)
    attacking_clan_names: List[str] = Field(default_factory=list)
    defending_clan_names: List[str] = Field(default_factory=list)
    development_level: int = 0
    offense_level: int = 0
    adjacent_territory_ids: List[int] = Field(default_factory=list)
    prosperity_score: int = 0
    population_income_bonus_percent: float = 0
    daily_income: float = 0
    weekly_income: float = 0
    resource_type: str = 'iron'
    resource_output: int = 1
    secondary_resource_type: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_validator('attacking_clans', 'defending_clans', mode='before')
    @classmethod
    def clan_objects_to_ids(cls, value):
        if value is None:
            return []
        return [item.id if hasattr(item, 'id') else item for item in value]


class TerritoryWithClans(TerritoryResponse):
    owner_clan_name: Optional[str] = None
    attacking_clan_names: List[str] = Field(default_factory=list)
    defending_clan_names: List[str] = Field(default_factory=list)


class TerritoryStats(BaseModel):
    total: int
    contested: int
    neutral: int
    active: int
    contested_percentage: int
    neutral_percentage: int
    active_percentage: int 


class TerritoryUpgradeRequest(BaseModel):
    upgrade_type: str
    levels: int = 1


class TerritoryOwnershipHistoryResponse(BaseModel):
    id: int
    territory_id: int
    clan_id: int
    clan_name: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    war_id: Optional[int] = None
    reason: str


class SeasonStartRequest(BaseModel):
    name: Optional[str] = None
    starting_influence: int = 500
    reset_development: bool = True
