from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Title(Base):
    __tablename__ = "titles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    name_en = Column(String(120), nullable=True)
    description_en = Column(Text, nullable=True)
    name_de = Column(String(120), nullable=True)
    description_de = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    assignments = relationship(
        "UserTitle",
        back_populates="title",
        cascade="all, delete-orphan",
    )


class UserTitle(Base):
    __tablename__ = "user_titles"
    __table_args__ = (
        UniqueConstraint("user_id", "title_id", name="uq_user_title"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title_id = Column(Integer, ForeignKey("titles.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", foreign_keys=[user_id], back_populates="title_assignments")
    assigned_by = relationship("User", foreign_keys=[assigned_by_user_id])
    title = relationship("Title", back_populates="assignments")
