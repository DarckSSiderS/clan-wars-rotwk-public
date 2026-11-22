from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ClanDiplomaticRelation(Base):
    __tablename__ = "clan_diplomatic_relations"
    __table_args__ = (
        UniqueConstraint("clan_low_id", "clan_high_id", name="uq_clan_diplomatic_pair"),
        CheckConstraint("clan_low_id < clan_high_id", name="ck_clan_diplomatic_pair_order"),
    )

    id = Column(Integer, primary_key=True)
    clan_low_id = Column(Integer, ForeignKey("clans.id", ondelete="CASCADE"), nullable=False, index=True)
    clan_high_id = Column(Integer, ForeignKey("clans.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="neutral", index=True)
    requested_by_clan_id = Column(Integer, ForeignKey("clans.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    clan_low = relationship("Clan", foreign_keys=[clan_low_id])
    clan_high = relationship("Clan", foreign_keys=[clan_high_id])
    requested_by_clan = relationship("Clan", foreign_keys=[requested_by_clan_id])
    events = relationship(
        "ClanDiplomacyEvent",
        back_populates="relation",
        cascade="all, delete-orphan",
        order_by="ClanDiplomacyEvent.created_at.desc()",
    )


class ClanDiplomacyEvent(Base):
    __tablename__ = "clan_diplomacy_events"

    id = Column(Integer, primary_key=True)
    relation_id = Column(
        Integer,
        ForeignKey("clan_diplomatic_relations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_clan_id = Column(Integer, ForeignKey("clans.id", ondelete="SET NULL"), nullable=True)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    previous_status = Column(String(32), nullable=False)
    new_status = Column(String(32), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    relation = relationship("ClanDiplomaticRelation", back_populates="events")
    actor_clan = relationship("Clan", foreign_keys=[actor_clan_id])
