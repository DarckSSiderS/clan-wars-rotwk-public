"""Opt-in seasonal economy storage; imported explicitly by the composition root."""

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, JSON, UniqueConstraint

from app.database import Base


class CycleEconomyState(Base):
    __tablename__ = 'cycle_economy_states'

    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), nullable=False)
    clan_id = Column(Integer, ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False)
    wallet = Column(JSON, nullable=False)
    relics = Column(JSON, nullable=False, default=dict)
    active_relics = Column(JSON, nullable=False, default=list)
    starters_chosen = Column(Boolean, nullable=False, default=False)
    revision = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint('season_id', 'clan_id', name='uq_cycle_economy_season_clan'),
        CheckConstraint('revision > 0', name='ck_cycle_economy_revision'),
    )


class CycleTerritoryUpgrade(Base):
    __tablename__ = 'cycle_territory_upgrades'

    season_id = Column(Integer, ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), primary_key=True)
    territory_id = Column(Integer, ForeignKey('territories.id', ondelete='RESTRICT'), primary_key=True)
    levels = Column(JSON, nullable=False, default=dict)
    revision = Column(Integer, nullable=False, default=1)

    __table_args__ = (CheckConstraint('revision > 0', name='ck_cycle_upgrade_revision'),)


class CycleEconomySnapshot(Base):
    __tablename__ = 'cycle_economy_snapshots'

    id = Column(Integer, primary_key=True)
    cycle_id = Column(Integer, ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False)
    state_id = Column(Integer, ForeignKey('cycle_economy_states.id', ondelete='RESTRICT'), nullable=False)
    effects = Column(JSON, nullable=False)
    territory_upgrades = Column(JSON, nullable=False)
    frozen_at = Column(DateTime(timezone=True), nullable=False)
    state_revision = Column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint('cycle_id', 'state_id', name='uq_cycle_economy_snapshot'),)
