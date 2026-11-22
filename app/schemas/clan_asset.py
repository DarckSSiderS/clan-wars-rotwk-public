from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Literal, Optional
from datetime import datetime


class ClanAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    description: Optional[str] = None
    bonus_type: str
    bonus_value: int = 0
    gold_cost: int = 0
    iron_cost: int = 0
    wood_cost: int = 0
    food_cost: int = 0
    mithril_cost: int = 0
    required_influence_level_1: int = 175
    required_influence_level_2: int = 525
    required_influence_level_3: int = 1050
    is_unique: bool = True
    is_available: bool = True
    max_level: int = 3
    upgrade_multiplier: int = 5

class ClanOwnedAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clan_id: int
    asset_id: int
    purchased_by: int
    purchased_at: datetime
    level: int = 1
    is_active: bool = False
    asset: ClanAssetResponse

class ClanAssetPurchase(BaseModel):
    asset_id: int


class ClanRelicLoadoutUpdate(BaseModel):
    asset_ids: list[int] = Field(default_factory=list, max_length=4)

    @field_validator("asset_ids")
    @classmethod
    def validate_unique_asset_ids(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("Реликвии в активном комплекте не должны повторяться")
        return value


class ClanAssetAdminPayload(BaseModel):
    key: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=2, max_length=160)
    description: Optional[str] = None
    bonus_type: Literal[
        "territory_points_percent",
        "war_win_points",
        "attack_power",
        "defense_power",
        "population_cost_percent",
        "gold_income_percent",
        "fortification_cost_percent",
        "population_growth_percent",
        "resource_income_flat",
    ]
    bonus_value: int = Field(default=0, ge=0, le=100)
    gold_cost: int = Field(default=0, ge=0, le=1000000)
    iron_cost: int = Field(default=0, ge=0, le=100000)
    wood_cost: int = Field(default=0, ge=0, le=100000)
    food_cost: int = Field(default=0, ge=0, le=100000)
    mithril_cost: int = Field(default=0, ge=0, le=100000)
    required_influence_level_1: int = Field(default=175, ge=0, le=1000000)
    required_influence_level_2: int = Field(default=525, ge=0, le=1000000)
    required_influence_level_3: int = Field(default=1050, ge=0, le=1000000)
    is_available: bool = True

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_influence_levels(self):
        if not (
            self.required_influence_level_1
            <= self.required_influence_level_2
            <= self.required_influence_level_3
        ):
            raise ValueError(
                "Пороги влияния должны возрастать от I к III уровню"
            )
        return self
