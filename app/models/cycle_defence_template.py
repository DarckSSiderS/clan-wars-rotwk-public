"""Explicit season/clan fallback, never reconstructed from historical orders."""
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, JSON, UniqueConstraint

from app.database import Base


class CycleDefenceTemplate(Base):
    __tablename__ = 'cycle_defence_templates'

    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), nullable=False)
    clan_id = Column(Integer, ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    assignments = Column(JSON, nullable=False, default=list)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    updated_by_user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    __table_args__ = (
        UniqueConstraint('season_id', 'clan_id', name='uq_cycle_defence_template_season_clan'),
        CheckConstraint('revision > 0', name='ck_cycle_defence_template_revision'),
    )
