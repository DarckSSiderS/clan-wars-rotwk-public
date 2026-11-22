from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint

from app.database import Base


class CampaignCycleRecord(Base):
    __tablename__ = 'campaign_cycles'

    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), nullable=False, index=True)
    number = Column(Integer, nullable=False)
    rule_version = Column(Integer, nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    preparation_at = Column(DateTime(timezone=True), nullable=False)
    settled_at = Column(DateTime(timezone=True), nullable=True)
    import_verified_at = Column(DateTime(timezone=True), nullable=True)
    season_end_requested = Column(Boolean, nullable=False, default=False)
    dependencies = Column(JSON, nullable=False, default=dict)
    planning_snapshot = Column(JSON, nullable=True)
    orders_frozen_at = Column(DateTime(timezone=True), nullable=True)
    battles_registered = Column(Boolean, nullable=False, default=False)
    revision = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint('season_id', 'number', name='uq_campaign_cycle_number'),
        CheckConstraint('number > 0 AND rule_version > 0 AND revision > 0', name='ck_campaign_cycle_positive'),
    )


class CampaignCyclePlan(Base):
    __tablename__ = 'campaign_cycle_plans'

    id = Column(Integer, primary_key=True)
    cycle_id = Column(Integer, ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False, index=True)
    clan_id = Column(Integer, ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False, index=True)
    revision = Column(Integer, nullable=False, default=1)
    orders = Column(JSON, nullable=False, default=list)
    snapshot = Column(JSON, nullable=True)
    frozen_at = Column(DateTime(timezone=True), nullable=True)
    updated_by_user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    __table_args__ = (
        UniqueConstraint('cycle_id', 'clan_id', name='uq_campaign_cycle_clan_plan'),
        CheckConstraint('revision > 0', name='ck_campaign_cycle_plan_revision'),
    )


class CampaignCyclePlanRevision(Base):
    __tablename__ = 'campaign_cycle_plan_revisions'
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey('campaign_cycle_plans.id', ondelete='RESTRICT'), nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    saved_at = Column(DateTime(timezone=True), nullable=False)
    actor_user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    orders = Column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint('plan_id', 'revision', name='uq_cycle_plan_revision_history'),)


class CycleScoutRequest(Base):
    __tablename__ = 'cycle_scout_requests'
    id = Column(Integer, primary_key=True)
    cycle_id = Column(Integer, ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False)
    clan_id = Column(Integer, ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False)
    territory_id = Column(Integer, ForeignKey('territories.id', ondelete='RESTRICT'), nullable=False)
    requested_at = Column(DateTime(timezone=True), nullable=False)
    actor_user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    scout_user_id = Column(Integer, ForeignKey('users.id', ondelete='RESTRICT'), nullable=True)
    scout_uuid = Column(String(128), nullable=True)
    report = Column(JSON, nullable=True)
    __table_args__ = (UniqueConstraint('cycle_id', 'clan_id', name='uq_cycle_scout_clan'),)
