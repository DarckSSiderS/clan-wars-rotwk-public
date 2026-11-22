"""Последний полностью сохранённый обход, отдельно от heartbeat процесса."""

from sqlalchemy import Column, DateTime, Integer, String

from app.database import Base


class CycleArenaScanState(Base):
    __tablename__ = 'cycle_arena_scan_state'
    source = Column(String(40), primary_key=True)
    covered_start = Column(DateTime(timezone=True), nullable=False)
    covered_end = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=False)
    replays_count = Column(Integer, nullable=False)
