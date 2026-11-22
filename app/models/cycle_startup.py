"""Opt-in startup ownership snapshot and durable one-season eligibility receipts."""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint

from app.database import Base


class CycleStartup(Base):
    __tablename__ = 'cycle_startups'

    season_id = Column(Integer, ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), primary_key=True)
    cycle_id = Column(Integer, ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    deadline = Column(DateTime(timezone=True), nullable=False)
    initial_owners = Column(JSON, nullable=False)
    initialized_at = Column(DateTime(timezone=True), nullable=False)
    expired_at = Column(DateTime(timezone=True))


class CycleStartupClan(Base):
    __tablename__ = 'cycle_startup_clans'

    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey('cycle_startups.season_id', ondelete='RESTRICT'), nullable=False)
    clan_id = Column(Integer, ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False)
    initial_owned = Column(JSON, nullable=False, default=list)
    slot = Column(Integer)
    qualified_at = Column(DateTime(timezone=True))
    selected_four = Column(JSON, nullable=False, default=list)
    selected_lands = Column(JSON, nullable=False, default=list)
    status = Column(String(20), nullable=False, default='pending')
    claimed_at = Column(DateTime(timezone=True))
    revision = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint('season_id', 'clan_id', name='uq_cycle_startup_clan'),
        UniqueConstraint('season_id', 'slot', name='uq_cycle_startup_slot'),
        CheckConstraint('slot IS NULL OR (slot >= 1 AND slot <= 6)', name='ck_cycle_startup_slot'),
        CheckConstraint('revision > 0', name='ck_cycle_startup_revision'),
    )


class CycleStartupIdentity(Base):
    __tablename__ = 'cycle_startup_identities'

    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey('cycle_startups.season_id', ondelete='RESTRICT'), nullable=False)
    clan_id = Column(Integer, ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False)
    source = Column(String(40), nullable=False)
    external_uuid = Column(String(80), nullable=False)

    __table_args__ = (UniqueConstraint('season_id', 'source', 'external_uuid', name='uq_cycle_startup_identity'),)
