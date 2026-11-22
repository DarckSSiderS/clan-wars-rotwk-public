from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class PasswordRecoveryToken(Base):
    __tablename__ = "password_recovery_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    email_hash = Column(String(64), nullable=False, index=True)
    token_hash = Column(String(64), nullable=True, unique=True, index=True)
    created_ip = Column(String(64), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    user = relationship("User", back_populates="password_recovery_tokens")

    __table_args__ = (
        Index(
            "ix_password_recovery_rate_email",
            "email_hash",
            "created_at",
        ),
        Index(
            "ix_password_recovery_rate_ip",
            "created_ip",
            "created_at",
        ),
    )
