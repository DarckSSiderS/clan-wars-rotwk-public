"""Independent cycle-market escrow, immutable transit and command receipts."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint

from app.database import Base


class CycleMarketOffer(Base):
    __tablename__ = 'cycle_market_offers'

    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey('campaign_seasons.id'), nullable=False)
    sender_clan_id = Column(Integer, ForeignKey('clans.id'), nullable=False)
    target_clan_id = Column(Integer, ForeignKey('clans.id'))
    accepter_clan_id = Column(Integer, ForeignKey('clans.id'))
    offered = Column(JSON, nullable=False)
    requested = Column(JSON, nullable=False)
    status = Column(String(24), nullable=False, default='pending')
    first_full_cycle = Column(Integer, nullable=False)
    expires_after_cycle = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True))
    revision = Column(Integer, nullable=False, default=1)


class CycleMarketCaravan(Base):
    __tablename__ = 'cycle_market_caravans'

    id = Column(Integer, primary_key=True)
    offer_id = Column(Integer, ForeignKey('cycle_market_offers.id'), nullable=False)
    recipient_clan_id = Column(Integer, ForeignKey('clans.id'), nullable=False)
    cargo = Column(JSON, nullable=False)
    route = Column(JSON, nullable=False)
    departed_at = Column(DateTime(timezone=True), nullable=False)
    arrives_at = Column(DateTime(timezone=True), nullable=False)
    delivered_at = Column(DateTime(timezone=True))
    revision = Column(Integer, nullable=False, default=1)
    __table_args__ = (UniqueConstraint('offer_id', 'recipient_clan_id', name='uq_cycle_market_caravan'),)


class CycleMarketCommand(Base):
    __tablename__ = 'cycle_market_commands'

    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey('campaign_seasons.id'), nullable=False)
    command_id = Column(String(128), nullable=False)
    payload = Column(JSON, nullable=False)
    result = Column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint('season_id', 'command_id', name='uq_cycle_market_command'),)
