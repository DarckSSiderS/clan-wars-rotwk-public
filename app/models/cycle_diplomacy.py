"""Opt-in season diplomacy. Import explicitly until parent registers migrations."""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint

from app.database import Base


class CycleDiplomacyPair(Base):
    __tablename__ = 'cycle_diplomacy_pairs'

    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), nullable=False, index=True)
    clan_low_id = Column(Integer, ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False)
    clan_high_id = Column(Integer, ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    allied_at = Column(DateTime(timezone=True), nullable=True)
    # Decimal strings avoid a database integer ceiling on user-selected terms.
    declarations = Column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint('season_id', 'clan_low_id', 'clan_high_id', name='uq_cycle_diplomacy_pair'),
        CheckConstraint('clan_low_id < clan_high_id AND revision > 0', name='ck_cycle_diplomacy_pair'),
    )


class CycleDiplomacyProposal(Base):
    """Immutable offer; acceptance/revocation lives in the event journal."""

    __tablename__ = 'cycle_diplomacy_proposals'

    id = Column(Integer, primary_key=True)
    pair_id = Column(Integer, ForeignKey('cycle_diplomacy_pairs.id', ondelete='RESTRICT'), nullable=False, index=True)
    sender_clan_id = Column(Integer, ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False)
    kind = Column(String(16), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    first_full_cycle = Column(Integer, nullable=False)
    expires_after_cycle = Column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("kind IN ('alliance', 'peace')", name='ck_cycle_diplomacy_proposal_kind'),
        CheckConstraint('first_full_cycle > 0 AND expires_after_cycle = first_full_cycle + 1',
                        name='ck_cycle_diplomacy_proposal_term'),
    )


class CycleDiplomacyEvent(Base):
    """Append-only service journal, also usable by a transactional notification outbox."""

    __tablename__ = 'cycle_diplomacy_events'

    id = Column(Integer, primary_key=True)
    pair_id = Column(Integer, ForeignKey('cycle_diplomacy_pairs.id', ondelete='RESTRICT'), nullable=False, index=True)
    cycle_id = Column(Integer, ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False)
    actor_clan_id = Column(Integer, ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False)
    actor_user_id = Column(Integer, ForeignKey('users.id', ondelete='RESTRICT'), nullable=True)
    kind = Column(String(32), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    # Only terminal events reference this field: at most one resolution per offer.
    resolved_proposal_id = Column(Integer, ForeignKey('cycle_diplomacy_proposals.id', ondelete='RESTRICT'),
                                  nullable=True, unique=True)
