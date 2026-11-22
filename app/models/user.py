from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    display_name = Column(String(120), nullable=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String)
    auth_version = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True)
    is_claimed = Column(Boolean, default=True, nullable=False)
    balance = Column(Integer, default=0)  # Баланс пользователя
    level = Column(Integer, default=1)  # Уровень пользователя
    experience = Column(Integer, default=0)  # Опыт пользователя
    avatar_url = Column(String, nullable=True)  # URL аватарки пользователя
    language = Column(String, default="ru")  # Язык пользователя (ru/eng)
    allow_clan_invites = Column(Boolean, default=True)  # Разрешить приглашения в клан
    role_id = Column(Integer, ForeignKey("roles.id"), default=2)  # По умолчанию роль "user"
    # Поля для контентмейкеров
    telegram_url = Column(String, nullable=True)  # URL Telegram
    twitch_url = Column(String, nullable=True)  # URL Twitch
    youtube_url = Column(String, nullable=True)  # URL YouTube
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    onboarding_completed_at = Column(DateTime(timezone=True), nullable=True)
    history_mode = Column(String(40), nullable=True)
    statistics_started_at = Column(DateTime(timezone=True), nullable=True)
    
    # Отношения
    role = relationship("Role", backref="users")
    clan_memberships = relationship("ClanMember", back_populates="user")
    clan_leader = relationship("Clan", back_populates="leader")
    clan_invites_sent = relationship("ClanInvite", foreign_keys="ClanInvite.inviter_id", back_populates="inviter")
    clan_invites_received = relationship("ClanInvite", foreign_keys="ClanInvite.invitee_id", back_populates="invitee")
    clan_applications = relationship("ClanApplication", foreign_keys="ClanApplication.user_id", back_populates="user")
    clan_applications_reviewed = relationship("ClanApplication", foreign_keys="ClanApplication.reviewed_by", back_populates="reviewer")
    items = relationship("UserItem", back_populates="user")
    achievements = relationship("UserAchievement", back_populates="user")
    war_participations = relationship("ClanWarParticipant", back_populates="user")
    clan_timeouts = relationship("ClanTimeout", back_populates="user")
    user_quests = relationship("UserQuest", back_populates="user") 
    external_identities = relationship(
        "ExternalPlayerIdentity",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    title_assignments = relationship(
        "UserTitle",
        foreign_keys="UserTitle.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    notifications = relationship(
        "UserNotification",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    password_recovery_tokens = relationship(
        "PasswordRecoveryToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sessions = relationship(
        "UserSession",
        foreign_keys="UserSession.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    impersonated_sessions = relationship(
        "UserSession",
        foreign_keys="UserSession.impersonated_by_user_id",
        back_populates="impersonated_by_user",
        passive_deletes="all",
    )
    security_audit_events = relationship(
        "SecurityAuditEvent",
        foreign_keys="SecurityAuditEvent.user_id",
        back_populates="user",
    )
    acted_security_audit_events = relationship(
        "SecurityAuditEvent",
        foreign_keys="SecurityAuditEvent.actor_user_id",
        back_populates="actor_user",
    )

    @property
    def titles(self):
        return [assignment.title for assignment in self.title_assignments if assignment.title]

    @property
    def external_identity_status(self):
        statuses = {
            identity.verification_status
            for identity in self.external_identities
        }
        for status in ("verified", "pending", "unverified"):
            if status in statuses:
                return status
        return None
