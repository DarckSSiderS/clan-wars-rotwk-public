from typing import Literal

from pydantic import BaseModel, Field, model_validator


ResourceName = Literal["gold", "iron", "wood", "food", "mithril"]
StrategyName = Literal["economic", "balanced", "military"]
RouteMode = Literal["auto", "land", "sea"]


class SimulationResources(BaseModel):
    gold: int = Field(default=500, ge=0, le=10_000_000)
    iron: int = Field(default=10, ge=0, le=1_000_000)
    wood: int = Field(default=10, ge=0, le=1_000_000)
    food: int = Field(default=5, ge=0, le=1_000_000)
    mithril: int = Field(default=2, ge=0, le=1_000_000)
    influence: int = Field(default=100, ge=0, le=1_000_000)


class EconomyScenarioInput(BaseModel):
    days: int = Field(default=30, ge=1, le=90)
    active_members: int = Field(default=12, ge=1, le=100)
    starting_territory_ids: list[int] = Field(min_length=1, max_length=20)
    starting_resources: SimulationResources = Field(default_factory=SimulationResources)
    capture_interval_days: int = Field(default=5, ge=1, le=30)
    strategy: StrategyName = "balanced"
    automatic_captures: bool = True
    production_multiplier_percent: int = Field(default=100, ge=25, le=300)
    cost_multiplier_percent: int = Field(default=100, ge=25, le=300)


class WarScenarioInput(BaseModel):
    source_territory_id: int = Field(ge=1)
    target_territory_id: int = Field(ge=1)
    route_mode: RouteMode = "auto"
    attacker_rating: int = Field(default=1000, ge=0, le=4000)
    defender_rating: int = Field(default=1000, ge=0, le=4000)
    match_count: int = Field(default=10, ge=1, le=100)
    team_size: int = Field(default=1, ge=1, le=8)
    clan_team: bool = True
    attacker_offense_level: int = Field(default=0, ge=0, le=10)
    attacker_naval_level: int = Field(default=0, ge=0, le=10)
    attacker_relic_power: int = Field(default=0, ge=0, le=100)
    defender_fortification_level: int = Field(default=0, ge=0, le=10)
    defender_development_level: int = Field(default=0, ge=0, le=10)
    defender_relic_power: int = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def require_different_territories(self):
        if self.source_territory_id == self.target_territory_id:
            raise ValueError("Source and target territories must be different.")
        return self


class TradeScenarioInput(BaseModel):
    source_territory_id: int = Field(ge=1)
    target_territory_id: int = Field(ge=1)
    route_mode: RouteMode = "auto"
    give_resource: ResourceName = "wood"
    give_amount: int = Field(default=20, ge=1, le=1_000_000)
    receive_resource: ResourceName = "iron"
    receive_amount: int = Field(default=20, ge=1, le=1_000_000)
    disruption_risk_percent: int = Field(default=0, ge=0, le=95)

    @model_validator(mode="after")
    def validate_trade(self):
        if self.source_territory_id == self.target_territory_id:
            raise ValueError("Source and target territories must be different.")
        if self.give_resource == self.receive_resource:
            raise ValueError("Trade resources must be different.")
        return self


class StrategicSandboxRequest(BaseModel):
    economy: EconomyScenarioInput
    war: WarScenarioInput
    trade: TradeScenarioInput
