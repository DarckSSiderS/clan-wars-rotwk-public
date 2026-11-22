from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, UniqueConstraint, Index, Boolean, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Clan(Base):
    __tablename__ = "clans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    motto = Column(String(160), nullable=True)
    description = Column(Text)
    leader_id = Column(Integer, ForeignKey("users.id"))
    avatar_url = Column(String, nullable=True)
    map_emblem_url = Column(String, nullable=True)
    map_color = Column(String(7), nullable=True, unique=True)
    map_color_change_used = Column(Boolean, default=False, nullable=False)
    level = Column(Integer, default=1)  # Уровень клана
    experience = Column(Integer, default=0)  # Опыт клана
    max_members = Column(Integer, default=20)  # Максимальное количество участников
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resources = Column(Integer, default=500)
    base_influence = Column(Integer, default=100, nullable=False)
    territory_points = Column(Integer, default=0)
    last_economy_tick = Column(DateTime(timezone=True), nullable=True)
    gold_income_remainder = Column(Float, default=0.0, nullable=False)
    next_attack_at = Column(DateTime(timezone=True), nullable=True)
    relic_loadout_locked_until = Column(DateTime(timezone=True), nullable=True)
    gold = Column(Integer, default=500)
    iron = Column(Integer, default=10)
    wood = Column(Integer, default=10)
    food = Column(Integer, default=5)
    mithril = Column(Integer, default=2)
    is_admin_clan = Column(Boolean, default=False, nullable=False)
    is_recruiting = Column(Boolean, default=True, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    preferred_patch = Column(String(20), default="all", nullable=False)
    
    # Отношения
    leader = relationship("User", back_populates="clan_leader")
    members = relationship("ClanMember", back_populates="clan", cascade="all, delete-orphan")
    applications = relationship("ClanApplication", back_populates="clan", cascade="all, delete-orphan")
    invites = relationship("ClanInvite", back_populates="clan", cascade="all, delete-orphan")
    owned_territories = relationship("Territory", back_populates="owner_clan")
    attacking_territories = relationship("Territory", secondary="territory_attacking_clans", back_populates="attacking_clans")
    defending_territories = relationship("Territory", secondary="territory_defending_clans", back_populates="defending_clans")
    attacking_wars = relationship("ClanWar", foreign_keys="ClanWar.attacking_clan_id", back_populates="attacking_clan")
    defending_wars = relationship("ClanWar", foreign_keys="ClanWar.defending_clan_id", back_populates="defending_clan")
    clan_timeouts = relationship("ClanTimeout", back_populates="clan", cascade="all, delete-orphan")
    level_events = relationship("ClanLevelEvent", back_populates="clan", cascade="all, delete-orphan")
    attack_point_spends = relationship("ClanAttackPointSpend", back_populates="clan", cascade="all, delete-orphan")
    war_deployments = relationship("WarDeployment", back_populates="clan", cascade="all, delete-orphan")

class ClanMember(Base):
    __tablename__ = "clan_members"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    clan_id = Column(Integer, ForeignKey("clans.id"))
    rank = Column(String, default="Новичок")  # Лидер, Маршал, Ветеран, Новичок
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    is_trader = Column(Boolean, default=False)
    is_warlord = Column(Boolean, default=False, nullable=False)
    
    # Отношения
    user = relationship("User", back_populates="clan_memberships")
    clan = relationship("Clan", back_populates="members")


class ClanMembershipPeriod(Base):
    __tablename__ = "clan_membership_periods"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    clan_id = Column(
        Integer,
        ForeignKey("clans.id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at = Column(DateTime(timezone=True), nullable=False, default=func.now)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    started_reason = Column(String(40), nullable=False, default="joined")
    ended_reason = Column(String(40), nullable=True)

    __table_args__ = (
        Index(
            "uq_clan_membership_periods_active_user",
            "user_id",
            unique=True,
            postgresql_where=ended_at.is_(None),
            sqlite_where=ended_at.is_(None),
        ),
        Index(
            "ix_clan_membership_periods_user_time",
            "user_id",
            "started_at",
            "ended_at",
        ),
        Index(
            "ix_clan_membership_periods_clan_time",
            "clan_id",
            "started_at",
            "ended_at",
        ),
    )


class ClanInvite(Base):
    __tablename__ = "clan_invites"

    id = Column(Integer, primary_key=True, index=True)
    clan_id = Column(Integer, ForeignKey("clans.id"))
    inviter_id = Column(Integer, ForeignKey("users.id"))
    invitee_id = Column(Integer, ForeignKey("users.id"))
    message = Column(Text, nullable=True)  # Сообщение с приглашением
    status = Column(String, default="pending")  # pending, accepted, declined
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Отношения
    clan = relationship("Clan", back_populates="invites")
    inviter = relationship("User", foreign_keys="ClanInvite.inviter_id", back_populates="clan_invites_sent")
    invitee = relationship("User", foreign_keys="ClanInvite.invitee_id", back_populates="clan_invites_received")

class ClanApplication(Base):
    __tablename__ = "clan_applications"

    id = Column(Integer, primary_key=True, index=True)
    clan_id = Column(Integer, ForeignKey("clans.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=True)  # Сообщение от пользователя
    status = Column(String, default="pending")  # pending, approved, rejected
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Кто рассмотрел заявку
    
    # Отношения
    clan = relationship("Clan", back_populates="applications")
    user = relationship("User", foreign_keys=[user_id], back_populates="clan_applications")
    reviewer = relationship("User", foreign_keys=[reviewed_by], back_populates="clan_applications_reviewed")
    
    # Индексы для быстрого поиска
    __table_args__ = (
        Index('ix_clan_applications_clan_id', 'clan_id'),
        Index('ix_clan_applications_user_id', 'user_id'),
        Index('ix_clan_applications_status', 'status'),
        # Уникальность: один пользователь может подать только одну активную заявку в клан
        UniqueConstraint('clan_id', 'user_id', name='uq_clan_user_application'),
    ) 
