from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

# Territory model moved to territory.py

class ClanWar(Base):
    __tablename__ = "clan_wars"

    id = Column(Integer, primary_key=True)
    territory_id = Column(Integer, ForeignKey("territories.id"), nullable=False)
    source_territory_id = Column(Integer, ForeignKey("territories.id"), nullable=True)
    attacking_clan_id = Column(Integer, ForeignKey("clans.id"), nullable=True)
    defending_clan_id = Column(Integer, ForeignKey("clans.id"), nullable=True)
    winner_clan_id = Column(Integer, ForeignKey("clans.id"), nullable=True)
    war_type = Column(String, nullable=False)   # 'neutral_capture' | 'territory_attack'
    status = Column(String, default="active")   # active | completed | canceled
    required_wins = Column(Integer, default=25)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ends_at = Column(DateTime(timezone=True), nullable=True)  # Started + snapshotted WAR_DURATION_HOURS
    ended_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    attacker_power = Column(Integer, default=0)
    defender_power = Column(Integer, default=0)
    influence_cost = Column(Integer, default=0)
    attack_route = Column(String(16), default="land", nullable=False)
    attacker_patch = Column(String(20), default="all", nullable=False)
    defender_patch = Column(String(20), nullable=True)
    scoring_version = Column(String(20), default="elo_team_v2", nullable=False)
    campaign_rule_set_id = Column(
        Integer,
        ForeignKey("campaign_rule_sets.id", ondelete="RESTRICT"),
        nullable=True,
    )
    rules_snapshot = Column(JSON, nullable=True)

    territory = relationship("Territory", foreign_keys=[territory_id])
    source_territory = relationship("Territory", foreign_keys=[source_territory_id])
    attacking_clan = relationship("Clan", foreign_keys=[attacking_clan_id], back_populates="attacking_wars")
    defending_clan = relationship("Clan", foreign_keys=[defending_clan_id], back_populates="defending_wars")
    winner_clan = relationship("Clan", foreign_keys=[winner_clan_id])
    participants = relationship("ClanWarParticipant", back_populates="war", cascade="all, delete-orphan")
    match_results = relationship(
        "ClanWarMatchResult",
        back_populates="war",
        cascade="all, delete-orphan",
    )
    campaign_rule_set = relationship("CampaignRuleSet")
    deployments = relationship("WarDeployment", back_populates="war", cascade="all, delete-orphan")
    attack_point_spends = relationship("ClanAttackPointSpend", back_populates="war")

    __table_args__ = (
        Index('ix_war_territory', 'territory_id'),
        Index('ix_war_status', 'status'),
        Index('ix_war_attacking_clan', 'attacking_clan_id'),
        Index('ix_war_defending_clan', 'defending_clan_id'),
        Index('ix_war_end', 'ends_at'),
    )

class ClanWarParticipant(Base):
    __tablename__ = "clan_war_participants"

    id = Column(Integer, primary_key=True)
    war_id = Column(Integer, ForeignKey("clan_wars.id"), nullable=False)
    clan_id = Column(Integer, ForeignKey("clans.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    war_points = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)

    war = relationship("ClanWar", back_populates="participants")
    clan = relationship("Clan")
    user = relationship("User", back_populates="war_participations")

    __table_args__ = (
        UniqueConstraint('war_id', 'user_id', name='uq_war_user'),
        Index('ix_cwp_war', 'war_id'),
        Index('ix_cwp_clan', 'clan_id'),
    )


class ClanWarMatchResult(Base):
    __tablename__ = "clan_war_match_results"

    id = Column(Integer, primary_key=True)
    war_id = Column(
        Integer,
        ForeignKey("clan_wars.id", ondelete="CASCADE"),
        nullable=False,
    )
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    played_at = Column(DateTime(timezone=True), nullable=False)
    winner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    loser_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    winner_clan_id = Column(Integer, ForeignKey("clans.id"), nullable=True)
    loser_clan_id = Column(Integer, ForeignKey("clans.id"), nullable=True)
    winner_base_points = Column(Float, nullable=False)
    winner_power_percent = Column(Integer, nullable=False, default=0)
    winner_power_bonus_points = Column(Float, nullable=False, default=0.0)
    winner_relic_bonus_points = Column(Float, nullable=False, default=0.0)
    winner_total_points = Column(Float, nullable=False)
    loser_base_points = Column(Float, nullable=False)
    loser_power_percent = Column(Integer, nullable=False, default=0)
    loser_power_bonus_points = Column(Float, nullable=False, default=0.0)
    loser_relic_bonus_points = Column(Float, nullable=False, default=0.0)
    loser_total_points = Column(Float, nullable=False)
    game_mode = Column(String(32), nullable=True)
    winner_team_size = Column(Integer, nullable=False, default=1)
    loser_team_size = Column(Integer, nullable=False, default=1)
    winner_clan_members = Column(Integer, nullable=False, default=1)
    loser_clan_members = Column(Integer, nullable=False, default=1)
    winner_team_bonus_percent = Column(Float, nullable=False, default=0.0)
    winner_team_bonus_points = Column(Float, nullable=False, default=0.0)
    loser_team_bonus_percent = Column(Float, nullable=False, default=0.0)
    loser_team_bonus_points = Column(Float, nullable=False, default=0.0)
    is_counted = Column(Boolean, nullable=False, default=True)
    rejection_reason = Column(String(120), nullable=True)
    admin_override = Column(Boolean, nullable=True)
    admin_override_reason = Column(String(500), nullable=True)
    admin_override_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    admin_override_at = Column(DateTime(timezone=True), nullable=True)
    patch_family = Column(String(20), nullable=True)
    winner_rating = Column(Float, nullable=True)
    loser_rating = Column(Float, nullable=True)
    winner_expected_probability = Column(Float, nullable=True)
    loser_expected_probability = Column(Float, nullable=True)
    scoring_version = Column(String(20), nullable=False, default="elo_team_v2")
    winner_deployment_id = Column(
        Integer,
        ForeignKey("war_deployments.id", ondelete="SET NULL"),
        nullable=True,
    )
    loser_deployment_id = Column(
        Integer,
        ForeignKey("war_deployments.id", ondelete="SET NULL"),
        nullable=True,
    )
    winner_participation_share = Column(Float, nullable=True)
    loser_participation_share = Column(Float, nullable=True)
    winner_eligibility_code = Column(String(80), nullable=True)
    loser_eligibility_code = Column(String(80), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    war = relationship("ClanWar", back_populates="match_results")
    match = relationship("Match")
    winner_user = relationship("User", foreign_keys=[winner_user_id])
    loser_user = relationship("User", foreign_keys=[loser_user_id])
    admin_override_by = relationship("User", foreign_keys=[admin_override_by_user_id])
    winner_clan = relationship("Clan", foreign_keys=[winner_clan_id])
    loser_clan = relationship("Clan", foreign_keys=[loser_clan_id])
    winner_deployment = relationship("WarDeployment", foreign_keys=[winner_deployment_id])
    loser_deployment = relationship("WarDeployment", foreign_keys=[loser_deployment_id])

    __table_args__ = (
        UniqueConstraint("war_id", "match_id", name="uq_war_match_result"),
        Index("ix_war_match_results_war_played", "war_id", "played_at"),
        Index("ix_war_match_results_match", "match_id"),
    )


class ClanTimeout(Base):
    __tablename__ = "clan_timeouts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    clan_id = Column(Integer, ForeignKey("clans.id"), nullable=False)
    timeout_until = Column(DateTime(timezone=True), nullable=False)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="clan_timeouts")
    clan = relationship("Clan", back_populates="clan_timeouts")

    __table_args__ = (
        Index('ix_ct_user', 'user_id'),
        Index('ix_ct_timeout_until', 'timeout_until'),
    ) 
