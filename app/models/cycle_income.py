"""Opt-in income tables. The composition root owns imports and migrations."""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, JSON, String

from app.database import Base


class CycleTerritoryProfile(Base):
    __tablename__ = 'cycle_territory_profiles'

    season_id = Column(Integer, ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), primary_key=True)
    territory_id = Column(Integer, ForeignKey('territories.id', ondelete='RESTRICT'), primary_key=True)
    base = Column(JSON, nullable=False)
    profile_material = Column(String(16), nullable=True)
    revision = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint('revision > 0', name='ck_cycle_income_profile_revision'),
        CheckConstraint("profile_material IS NULL OR profile_material IN ('iron','wood','food','mithril')",
                        name='ck_cycle_income_profile_material'),
    )


class CycleIncomeAccrual(Base):
    """One durable high-water receipt per wallet, including exact residuals."""

    __tablename__ = 'cycle_income_accruals'

    state_id = Column(Integer, ForeignKey('cycle_economy_states.id', ondelete='RESTRICT'), primary_key=True)
    accrued_through = Column(DateTime(timezone=True), nullable=False)
    residuals = Column(JSON, nullable=False, default=dict)
    revision = Column(Integer, nullable=False, default=1)

    __table_args__ = (CheckConstraint('revision > 0', name='ck_cycle_income_accrual_revision'),)
