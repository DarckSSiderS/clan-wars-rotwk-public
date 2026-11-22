from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class CampaignRuleSet(Base):
    __tablename__ = "campaign_rule_sets"

    id = Column(Integer, primary_key=True)
    version = Column(Integer, nullable=False, unique=True, index=True)
    values = Column(JSON, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason = Column(String(500), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_campaign_rule_sets_active",
            "is_active",
            unique=True,
            postgresql_where=is_active.is_(True),
            sqlite_where=is_active.is_(True),
        ),
    )


class CampaignSettings(Base):
    __tablename__ = "campaign_settings"

    id = Column(Integer, primary_key=True, default=1)
    patch_202_enabled = Column(Boolean, nullable=False, default=True)
    ennorath_enabled = Column(Boolean, nullable=False, default=True)
    updated_by = Column(String(100), nullable=True)
    replay_cursor_ms = Column(BigInteger, nullable=True)
    is_paused = Column(Boolean, nullable=False, default=False)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    paused_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    pause_reason = Column(String(500), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ReplaySyncState(Base):
    __tablename__ = "replay_sync_states"

    replay_id = Column(String(120), primary_key=True)
    status = Column(String(24), nullable=False, index=True)
    patch_family = Column(String(20), nullable=True, index=True)
    patch_name = Column(String(160), nullable=True)
    reason = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=1)
    first_seen_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_attempt_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    imported_at = Column(DateTime(timezone=True), nullable=True)


class CampaignSeason(Base):
    __tablename__ = "campaign_seasons"

    id = Column(Integer, primary_key=True)
    number = Column(Integer, nullable=False, unique=True, index=True)
    name = Column(String(120), nullable=False)
    status = Column(String(20), nullable=False, default="active", index=True)
    starting_influence = Column(Integer, nullable=False, default=100)
    reset_development = Column(Boolean, nullable=False, default=True)
    starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ends_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    rules_snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    results = relationship(
        "CampaignSeasonClanResult",
        back_populates="season",
        cascade="all, delete-orphan",
        order_by="CampaignSeasonClanResult.rank",
    )

    __table_args__ = (
        Index(
            "uq_campaign_seasons_active",
            "status",
            unique=True,
            postgresql_where=status == "active",
            sqlite_where=status == "active",
        ),
    )


class CampaignSeasonClanResult(Base):
    __tablename__ = "campaign_season_clan_results"

    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey("campaign_seasons.id", ondelete="CASCADE"), nullable=False, index=True)
    clan_id = Column(Integer, ForeignKey("clans.id", ondelete="SET NULL"), nullable=True, index=True)
    clan_name = Column(String(160), nullable=False)
    clan_avatar_url = Column(String, nullable=True)
    clan_map_color = Column(String(7), nullable=True)
    rank = Column(Integer, nullable=False)
    influence = Column(Integer, nullable=False, default=0)
    base_influence = Column(Integer, nullable=False, default=0)
    territory_count = Column(Integer, nullable=False, default=0)
    wars_won = Column(Integer, nullable=False, default=0)
    wars_lost = Column(Integer, nullable=False, default=0)
    defenses_won = Column(Integer, nullable=False, default=0)
    gold = Column(Integer, nullable=False, default=0)
    iron = Column(Integer, nullable=False, default=0)
    wood = Column(Integer, nullable=False, default=0)
    food = Column(Integer, nullable=False, default=0)
    mithril = Column(Integer, nullable=False, default=0)
    captured_at = Column(DateTime(timezone=True), nullable=False)

    season = relationship("CampaignSeason", back_populates="results")
    clan = relationship("Clan")

    __table_args__ = (
        UniqueConstraint("season_id", "clan_id", name="uq_campaign_season_clan"),
        Index("ix_campaign_season_result_rank", "season_id", "rank"),
    )
