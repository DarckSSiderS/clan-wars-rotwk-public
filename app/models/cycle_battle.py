from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint

from app.database import Base


class CycleTerritoryBattle(Base):
    __tablename__ = 'cycle_territory_battles'
    id = Column(Integer, primary_key=True)
    cycle_id = Column(Integer, ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False, index=True)
    territory_id = Column(Integer, ForeignKey('territories.id', ondelete='RESTRICT'), nullable=False)
    owner_clan_id = Column(Integer, ForeignKey('clans.id', ondelete='SET NULL'))
    winner_clan_id = Column(Integer, ForeignKey('clans.id', ondelete='SET NULL'))
    recalculated_winner_clan_id = Column(Integer, ForeignKey('clans.id', ondelete='SET NULL'))
    sides = Column(JSON, nullable=False)
    completed_at = Column(DateTime(timezone=True))
    ownership_applied_at = Column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('cycle_id', 'territory_id', name='uq_cycle_territory_battle'),)


class CycleMatchContribution(Base):
    __tablename__ = 'cycle_match_contributions'
    id = Column(Integer, primary_key=True)
    battle_id = Column(Integer, ForeignKey('cycle_territory_battles.id', ondelete='RESTRICT'), nullable=False, index=True)
    replay_id = Column(String(120), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    clan_id = Column(Integer, ForeignKey('clans.id', ondelete='SET NULL'))
    points = Column(Numeric(28, 12), nullable=False)
    counted = Column(Boolean, nullable=False, default=True)
    reason = Column(String(500), nullable=False)
    calculation = Column(JSON)
    review_reason = Column(String(500))
    reviewed_by_user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    __table_args__ = (UniqueConstraint('battle_id', 'replay_id', 'user_id', name='uq_cycle_match_player'),)


class CycleScoreAdjustment(Base):
    __tablename__ = 'cycle_score_adjustments'
    id = Column(Integer, primary_key=True)
    battle_id = Column(Integer, ForeignKey('cycle_territory_battles.id', ondelete='RESTRICT'), nullable=False, index=True)
    clan_id = Column(Integer, ForeignKey('clans.id', ondelete='SET NULL'))
    command_id = Column(String(120), nullable=False)
    points = Column(Numeric(28, 12), nullable=False)
    reason = Column(String(500), nullable=False)
    actor_user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    __table_args__ = (UniqueConstraint('battle_id', 'command_id', name='uq_cycle_adjustment_command'),)


class CycleOwnershipCorrection(Base):
    __tablename__ = 'cycle_ownership_corrections'
    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), nullable=False)
    battle_id = Column(Integer, ForeignKey('cycle_territory_battles.id', ondelete='RESTRICT'), nullable=False, index=True)
    current_cycle_id = Column(Integer, ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False)
    territory_id = Column(Integer, ForeignKey('territories.id', ondelete='RESTRICT'), nullable=False)
    previous_owner_clan_id = Column(Integer, ForeignKey('clans.id', ondelete='SET NULL'))
    new_owner_clan_id = Column(Integer, ForeignKey('clans.id', ondelete='SET NULL'))
    actor_user_id = Column(Integer, ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    command_id = Column(String(120), nullable=False)
    preview_token = Column(String(64), nullable=False)
    reason = Column(String(500), nullable=False)
    applied_at = Column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint('season_id', 'command_id', name='uq_cycle_ownership_command'),)


class CycleLateReplayDecision(Base):
    __tablename__ = 'cycle_late_replay_decisions'
    id = Column(Integer, primary_key=True)
    battle_id = Column(Integer, ForeignKey('cycle_territory_battles.id', ondelete='RESTRICT'), nullable=False, index=True)
    match_id = Column(Integer, ForeignKey('matches.id', ondelete='RESTRICT'), nullable=False)
    command_id = Column(String(120), nullable=False)
    preview_token = Column(String(64), nullable=False)
    counted = Column(Boolean, nullable=False)
    reason = Column(String(500), nullable=False)
    actor_user_id = Column(Integer, ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    decided_at = Column(DateTime(timezone=True), nullable=False)
    user_ids = Column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint('battle_id', 'command_id', name='uq_cycle_late_replay_command'),)
