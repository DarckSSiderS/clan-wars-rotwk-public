"""Opt-in cycle aggregate storage; registration/migration is owned by the caller."""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, JSON, UniqueConstraint

from app.database import Base


class CycleReinforcementState(Base):
    __tablename__ = 'cycle_reinforcement_states'

    id = Column(Integer, primary_key=True)
    cycle_id = Column(Integer, ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    payload = Column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint('cycle_id', name='uq_cycle_reinforcement_state_cycle'),
        CheckConstraint('revision > 0', name='ck_cycle_reinforcement_state_revision'),
    )
