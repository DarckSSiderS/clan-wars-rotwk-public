from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint

from app.database import Base


class CycleInterception(Base):
    __tablename__ = 'cycle_interceptions'
    id = Column(Integer, primary_key=True)
    cycle_id = Column(Integer, ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False, index=True)
    dispatch_id = Column(String(120), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    verified_revision = Column(Integer)
    verified_at = Column(DateTime(timezone=True))
    source_cursor = Column(String(500))
    covered_start = Column(DateTime(timezone=True))
    covered_end = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    original_applied_result = Column(JSON, nullable=True)
    __table_args__ = (UniqueConstraint('cycle_id', 'dispatch_id', name='uq_cycle_interception_dispatch'),)


class CycleInterceptionContribution(Base):
    __tablename__ = 'cycle_interception_contributions'
    id = Column(Integer, primary_key=True)
    interception_id = Column(Integer, ForeignKey('cycle_interceptions.id', ondelete='RESTRICT'), nullable=False, index=True)
    replay_id = Column(String(120), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    # Зафиксированная сторона перехвата, не текущий клан игрока.
    side_clan_id = Column(Integer, nullable=False)
    points = Column(Numeric(28, 12), nullable=False)
    counted = Column(Boolean, nullable=False)
    reason = Column(String(500), nullable=False)
    calculation = Column(JSON, nullable=False)
    review_counted = Column(Boolean, nullable=True)
    __table_args__ = (UniqueConstraint('interception_id', 'replay_id', 'user_id', name='uq_interception_match_player'),)


class CycleInterceptionReviewCommand(Base):
    __tablename__ = 'cycle_interception_review_commands'
    id = Column(Integer, primary_key=True)
    interception_id = Column(Integer, ForeignKey('cycle_interceptions.id', ondelete='RESTRICT'), nullable=False, index=True)
    command_id = Column(String(120), nullable=False)
    action = Column(String(40), nullable=False)
    actor_user_id = Column(Integer, ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    reason = Column(String(500), nullable=False)
    expected_revision = Column(Integer, nullable=False)
    payload = Column(JSON, nullable=False)
    before = Column(JSON, nullable=False)
    after = Column(JSON, nullable=False)
    result = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint('interception_id', 'command_id', name='uq_interception_review_command'),)


class CycleInterceptionAdjustment(Base):
    __tablename__ = 'cycle_interception_adjustments'
    id = Column(Integer, primary_key=True)
    interception_id = Column(Integer, ForeignKey('cycle_interceptions.id', ondelete='RESTRICT'), nullable=False, index=True)
    command_id = Column(String(120), nullable=False)
    side_clan_id = Column(Integer, nullable=False)
    points = Column(Numeric(28, 12), nullable=False)
    actor_user_id = Column(Integer, ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    reason = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint('interception_id', 'command_id', name='uq_interception_adjustment_command'),)
