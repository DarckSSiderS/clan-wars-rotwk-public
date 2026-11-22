from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class WarDeployment(Base):
    __tablename__ = "war_deployments"

    id = Column(Integer, primary_key=True)
    war_id = Column(Integer, ForeignKey("clan_wars.id", ondelete="CASCADE"), nullable=False)
    clan_id = Column(Integer, ForeignKey("clans.id", ondelete="CASCADE"), nullable=False)
    claim_sequence = Column(Integer, nullable=False)
    source_territory_id = Column(
        Integer,
        ForeignKey("territories.id", ondelete="SET NULL"),
        nullable=True,
    )
    territory_count_snapshot = Column(Integer, nullable=False)
    defense_rule = Column(String(64), nullable=False)
    initial_role = Column(String(16), nullable=False)
    current_role = Column(String(16), nullable=False)
    eligibility_scope = Column(String(20), nullable=False)
    assigned_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    warlord_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    warlord_username_snapshot = Column(String(120), nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=False)
    campaign_rule_set_id = Column(
        Integer,
        ForeignKey("campaign_rule_sets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rule_version = Column(Integer, nullable=False)
    attack_lock_released_at = Column(DateTime(timezone=True), nullable=True)
    role_changed_at = Column(DateTime(timezone=True), nullable=True)

    war = relationship("ClanWar", back_populates="deployments")
    clan = relationship("Clan", back_populates="war_deployments")
    source_territory = relationship("Territory", foreign_keys=[source_territory_id])
    assigned_by_user = relationship("User", foreign_keys=[assigned_by_user_id])
    warlord_user = relationship("User", foreign_keys=[warlord_user_id])
    campaign_rule_set = relationship("CampaignRuleSet")
    members = relationship(
        "WarDeploymentMember",
        back_populates="deployment",
        cascade="all, delete-orphan",
        order_by="WarDeploymentMember.id",
    )

    __table_args__ = (
        UniqueConstraint("war_id", "clan_id", name="uq_war_deployment_war_clan"),
        UniqueConstraint("war_id", "claim_sequence", name="uq_war_deployment_claim_sequence"),
        Index("ix_war_deployments_clan_role", "clan_id", "current_role"),
    )


class WarDeploymentMember(Base):
    __tablename__ = "war_deployment_members"

    id = Column(Integer, primary_key=True)
    deployment_id = Column(
        Integer,
        ForeignKey("war_deployments.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    external_uuid_snapshot = Column(String(80), nullable=False)
    nickname_snapshot = Column(String(120), nullable=False)
    username_snapshot = Column(String(120), nullable=False)
    avatar_url_snapshot = Column(String, nullable=True)
    membership_started_at = Column(DateTime(timezone=True), nullable=False)
    assigned_at = Column(DateTime(timezone=True), nullable=False)
    released_at = Column(DateTime(timezone=True), nullable=True)

    deployment = relationship("WarDeployment", back_populates="members")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("deployment_id", "user_id", name="uq_war_deployment_member"),
        Index(
            "uq_active_attack_deployment_member_user",
            "user_id",
            unique=True,
            postgresql_where=released_at.is_(None),
            sqlite_where=released_at.is_(None),
        ),
        Index("ix_war_deployment_members_deployment", "deployment_id"),
    )
