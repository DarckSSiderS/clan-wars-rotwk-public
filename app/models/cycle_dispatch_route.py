"""Неизменяемая география отправки отдельно от строгого состояния игровых правил."""
from sqlalchemy import Column, ForeignKey, Integer, JSON, String, UniqueConstraint

from app.database import Base


class CycleDispatchRoute(Base):
    __tablename__ = 'cycle_dispatch_routes'

    id = Column(Integer, primary_key=True)
    cycle_id = Column(Integer, ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False, index=True)
    dispatch_id = Column(String(120), nullable=False)
    origin_territory_id = Column(Integer, nullable=True)
    snapshot = Column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint('cycle_id', 'dispatch_id', name='uq_cycle_dispatch_route'),
    )
