from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class MarketOffer(Base):
    __tablename__ = "market_offers"

    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey("campaign_seasons.id"), nullable=True, index=True)
    creator_clan_id = Column(Integer, ForeignKey("clans.id"), nullable=False, index=True)
    accepted_by_clan_id = Column(Integer, ForeignKey("clans.id"), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    accepted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    give_resource = Column(String(20), nullable=False)
    give_amount = Column(Integer, nullable=False)
    receive_resource = Column(String(20), nullable=False)
    receive_amount = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="open", index=True)
    route = Column(JSON, nullable=True)
    route_steps = Column(Integer, nullable=True)
    creator_shipping_cost = Column(Integer, nullable=True)
    accepter_shipping_cost = Column(Integer, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    eta = Column(DateTime(timezone=True), nullable=True, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    creator_clan = relationship("Clan", foreign_keys=[creator_clan_id])
    accepted_by_clan = relationship("Clan", foreign_keys=[accepted_by_clan_id])
    caravans = relationship(
        "TradeCaravan",
        back_populates="offer",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_market_offers_status_created", "status", "created_at"),
    )


class TradeCaravan(Base):
    __tablename__ = "trade_caravans"

    id = Column(Integer, primary_key=True)
    offer_id = Column(
        Integer,
        ForeignKey("market_offers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_clan_id = Column(Integer, ForeignKey("clans.id"), nullable=False)
    to_clan_id = Column(Integer, ForeignKey("clans.id"), nullable=False)
    resource = Column(String(20), nullable=False)
    amount = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="traveling", index=True)
    route = Column(JSON, nullable=False)
    departed_at = Column(DateTime(timezone=True), nullable=False)
    eta = Column(DateTime(timezone=True), nullable=False, index=True)
    arrived_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    offer = relationship("MarketOffer", back_populates="caravans")
    from_clan = relationship("Clan", foreign_keys=[from_clan_id])
    to_clan = relationship("Clan", foreign_keys=[to_clan_id])

    __table_args__ = (
        Index("ix_trade_caravans_status_eta", "status", "eta"),
    )
