from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ClanLevelEvent(Base):
    __tablename__ = "clan_level_events"

    id = Column(Integer, primary_key=True)
    clan_id = Column(Integer, ForeignKey("clans.id", ondelete="CASCADE"), nullable=False)
    previous_level = Column(Integer, nullable=False)
    new_level = Column(Integer, nullable=False)
    active_member_count = Column(Integer, nullable=False)
    territory_count = Column(Integer, nullable=False)
    influence = Column(Integer, nullable=False)
    campaign_rule_set_id = Column(
        Integer,
        ForeignKey("campaign_rule_sets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rule_version = Column(Integer, nullable=False)
    reason = Column(String(120), nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    clan = relationship("Clan", back_populates="level_events")
    campaign_rule_set = relationship("CampaignRuleSet")

    __table_args__ = (
        Index("ix_clan_level_events_clan_time", "clan_id", "occurred_at"),
    )


class ClanAttackPointSpend(Base):
    __tablename__ = "clan_attack_point_spends"

    id = Column(Integer, primary_key=True)
    clan_id = Column(Integer, ForeignKey("clans.id", ondelete="CASCADE"), nullable=False)
    war_id = Column(
        Integer,
        ForeignKey("clan_wars.id", ondelete="SET NULL"),
        nullable=True,
    )
    spent_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    origin = Column(String(40), nullable=False)
    spent_at = Column(DateTime(timezone=True), nullable=False)
    recover_at = Column(DateTime(timezone=True), nullable=False)
    level_snapshot = Column(Integer, nullable=False)
    capacity_snapshot = Column(Integer, nullable=False)
    campaign_rule_set_id = Column(
        Integer,
        ForeignKey("campaign_rule_sets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rule_version = Column(Integer, nullable=False)
    refunded_at = Column(DateTime(timezone=True), nullable=True)
    refunded_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    refund_reason = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    clan = relationship("Clan", back_populates="attack_point_spends")
    war = relationship("ClanWar", back_populates="attack_point_spends")
    spent_by_user = relationship("User", foreign_keys=[spent_by_user_id])
    refunded_by_user = relationship("User", foreign_keys=[refunded_by_user_id])
    campaign_rule_set = relationship("CampaignRuleSet")

    __table_args__ = (
        Index(
            "uq_attack_point_spend_war_clan",
            "war_id",
            "clan_id",
            unique=True,
            postgresql_where=war_id.is_not(None),
            sqlite_where=war_id.is_not(None),
        ),
        Index("ix_attack_point_clan_recover", "clan_id", "recover_at"),
    )
