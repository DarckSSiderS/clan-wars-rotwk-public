from sqlalchemy import Column, Integer, String, Text, JSON, DateTime, ForeignKey, Boolean, ARRAY, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.core.campaign_rules import default_campaign_rule_values


_DEFAULT_CAMPAIGN_RULES = default_campaign_rule_values()


class Territory(Base):
    __tablename__ = "territories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    region = Column(String(100), nullable=False, index=True)
    description = Column(Text)
    svg_path_data = Column(Text, nullable=False)  # SVG path data для уникальной идентификации
    owner_clan_id = Column(Integer, ForeignKey("clans.id"), nullable=True)
    resource_wealth = Column(Integer, default=0)
    influence_value = Column(Integer, default=0, nullable=False)
    required_influence = Column(Integer, default=30, nullable=False)
    strategic_value = Column(Float, default=0.0)  # 0-10, среднее уровней развития
    population = Column(Integer, default=0)
    fortifications = Column(Integer, default=0)  # 0-10
    trade_routes = Column(JSON().with_variant(ARRAY(String), "postgresql"), default=list)
    special_resources = Column(JSON().with_variant(ARRAY(String), "postgresql"), default=list)
    climate = Column(String(100), default='temperate')
    terrain = Column(String(100), default='plains')
    status = Column(String(50), default='neutral')  # neutral, contested, active
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    development_level = Column(Integer, default=0)
    offense_level = Column(Integer, default=0)
    adjacent_territory_ids = Column(JSON, default=list)
    resource_type = Column(String(20), default='iron')
    resource_output = Column(Integer, default=1)
    secondary_resource_type = Column(String(20), nullable=True)
    is_playable = Column(Boolean, default=True, nullable=False)
    is_coastal = Column(Boolean, default=False, nullable=False)
    has_port = Column(Boolean, default=False, nullable=False)
    port_level = Column(Integer, default=0, nullable=False)
    fleet_level = Column(Integer, default=0, nullable=False)
    required_territories = Column(Integer, default=0, nullable=False)
    stronghold_power = Column(Integer, default=0, nullable=False)
    owned_since = Column(DateTime(timezone=True), nullable=True)
    last_weekly_payout_at = Column(DateTime(timezone=True), nullable=True)
    resource_income_ready_at = Column(DateTime(timezone=True), nullable=True)
    last_resource_payout_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    owner_clan = relationship("Clan", back_populates="owned_territories")
    attacking_clans = relationship("Clan", secondary="territory_attacking_clans", back_populates="attacking_territories")
    defending_clans = relationship("Clan", secondary="territory_defending_clans", back_populates="defending_territories")

    @property
    def owner_clan_name(self):
        return self.owner_clan.name if self.owner_clan else None

    @property
    def owner_clan_avatar_url(self):
        return self.owner_clan.avatar_url if self.owner_clan else None

    @property
    def owner_clan_map_emblem_url(self):
        return self.owner_clan.map_emblem_url if self.owner_clan else None

    @property
    def owner_clan_map_color(self):
        if not self.owner_clan or self.owner_clan.is_admin_clan:
            return None
        return self.owner_clan.map_color

    @property
    def owner_clan_is_admin(self):
        return bool(self.owner_clan and self.owner_clan.is_admin_clan)

    @property
    def attacking_clan_names(self):
        return [clan.name for clan in self.attacking_clans if clan.name]

    @property
    def defending_clan_names(self):
        return [clan.name for clan in self.defending_clans if clan.name]

    @property
    def prosperity_score(self):
        population = self.population or 0
        stronghold_value = (self.stronghold_power or 0) * 40
        return max(1, int((self.resource_wealth or 0) + (self.strategic_value or 0) * 10 + population / 1000 + (self.development_level or 0) * 15 + stronghold_value))

    @property
    def population_income_bonus_percent(self) -> float:
        population = min(
            int(_DEFAULT_CAMPAIGN_RULES["POPULATION_INCOME_BONUS_CAP_PERCENT"])
            * int(_DEFAULT_CAMPAIGN_RULES["POPULATION_PER_INCOME_PERCENT"]),
            max(0, self.population or 0),
        )
        return round(
            population / int(_DEFAULT_CAMPAIGN_RULES["POPULATION_PER_INCOME_PERCENT"]),
            2,
        )

    @property
    def population_development_income_bonus_percent(self) -> int:
        level = max(0, int(self.development_level or 0))
        break_level = int(
            _DEFAULT_CAMPAIGN_RULES["POPULATION_DEVELOPMENT_BONUS_BREAK_LEVEL"]
        )
        return (
            min(level, break_level)
            * int(
                _DEFAULT_CAMPAIGN_RULES[
                    "POPULATION_DEVELOPMENT_BONUS_FIRST_LEVELS_PERCENT"
                ]
            )
            + max(0, level - break_level)
            * int(
                _DEFAULT_CAMPAIGN_RULES[
                    "POPULATION_DEVELOPMENT_BONUS_LATER_LEVELS_PERCENT"
                ]
            )
        )

    @property
    def daily_income(self) -> float:
        base_income = max(0, self.resource_wealth or 0)
        return round(
            base_income
            * (
                1
                + (
                    self.population_income_bonus_percent
                    + self.population_development_income_bonus_percent
                )
                / 100
            ),
            2,
        )

    @property
    def weekly_income(self) -> float:
        """Совместимое недельное представление суточного дохода."""
        return round(self.daily_income * 7, 2)

    def calculate_strategic_value(self) -> float:
        levels = [
            self.development_level or 0,
            self.fortifications or 0,
            self.offense_level or 0,
        ]
        if self.has_port:
            levels.append(max(self.port_level or 0, self.fleet_level or 0))
        return round(sum(levels) / len(levels), 1)

    @property
    def is_great_stronghold(self) -> bool:
        return (self.stronghold_power or 0) > 0


# Association tables for many-to-many relationships
class TerritoryAttackingClans(Base):
    __tablename__ = "territory_attacking_clans"
    
    territory_id = Column(Integer, ForeignKey("territories.id"), primary_key=True)
    clan_id = Column(Integer, ForeignKey("clans.id"), primary_key=True)


class TerritoryDefendingClans(Base):
    __tablename__ = "territory_defending_clans"
    
    territory_id = Column(Integer, ForeignKey("territories.id"), primary_key=True)
    clan_id = Column(Integer, ForeignKey("clans.id"), primary_key=True)


class TerritoryOwnershipHistory(Base):
    __tablename__ = "territory_ownership_history"

    id = Column(Integer, primary_key=True, index=True)
    territory_id = Column(Integer, ForeignKey("territories.id"), nullable=False, index=True)
    clan_id = Column(Integer, ForeignKey("clans.id"), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ended_at = Column(DateTime(timezone=True), nullable=True, index=True)
    war_id = Column(
        Integer,
        ForeignKey("clan_wars.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reason = Column(String(40), nullable=False, default="capture")

    territory = relationship("Territory")
    clan = relationship("Clan")
    war = relationship("ClanWar")
