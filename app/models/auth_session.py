from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    false,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class OAuthLoginState(Base):
    __tablename__ = "oauth_login_states"

    id = Column(Integer, primary_key=True, index=True)
    state_hash = Column(String(64), unique=True, index=True, nullable=False)
    flow_hash = Column(String(64), index=True, nullable=False)
    return_to = Column(String(500), nullable=False, default="/")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    is_impersonation = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    impersonated_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="sessions",
    )
    impersonated_by_user = relationship(
        "User",
        foreign_keys=[impersonated_by_user_id],
        back_populates="impersonated_sessions",
    )


class SecurityAuditEvent(Base):
    __tablename__ = "security_audit_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type = Column(String(60), index=True, nullable=False)
    ip_address = Column(String(64), nullable=True)
    event_metadata = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="security_audit_events",
    )
    actor_user = relationship(
        "User",
        foreign_keys=[actor_user_id],
        back_populates="acted_security_audit_events",
    )
