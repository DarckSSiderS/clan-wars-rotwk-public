"""Season-specific diplomatic relations, proposals and append-only events."""

from alembic import op
import sqlalchemy as sa

revision = 'h0w1x2y3z4a5'
down_revision = 'g9v0w1x2y3z4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cycle_diplomacy_pairs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('season_id', sa.Integer(), sa.ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('clan_low_id', sa.Integer(), sa.ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('clan_high_id', sa.Integer(), sa.ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('allied_at', sa.DateTime(timezone=True)),
        sa.Column('declarations', sa.JSON(), nullable=False),
        sa.UniqueConstraint('season_id', 'clan_low_id', 'clan_high_id', name='uq_cycle_diplomacy_pair'),
        sa.CheckConstraint('clan_low_id < clan_high_id AND revision > 0', name='ck_cycle_diplomacy_pair'),
    )
    op.create_index('ix_cycle_diplomacy_pairs_season_id', 'cycle_diplomacy_pairs', ['season_id'])
    op.create_table(
        'cycle_diplomacy_proposals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pair_id', sa.Integer(), sa.ForeignKey('cycle_diplomacy_pairs.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('sender_clan_id', sa.Integer(), sa.ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('first_full_cycle', sa.Integer(), nullable=False),
        sa.Column('expires_after_cycle', sa.Integer(), nullable=False),
        sa.CheckConstraint("kind IN ('alliance', 'peace')", name='ck_cycle_diplomacy_proposal_kind'),
        sa.CheckConstraint('first_full_cycle > 0 AND expires_after_cycle = first_full_cycle + 1', name='ck_cycle_diplomacy_proposal_term'),
    )
    op.create_index('ix_cycle_diplomacy_proposals_pair_id', 'cycle_diplomacy_proposals', ['pair_id'])
    op.create_table(
        'cycle_diplomacy_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pair_id', sa.Integer(), sa.ForeignKey('cycle_diplomacy_pairs.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('actor_clan_id', sa.Integer(), sa.ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT')),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('resolved_proposal_id', sa.Integer(), sa.ForeignKey('cycle_diplomacy_proposals.id', ondelete='RESTRICT'), unique=True),
    )
    op.create_index('ix_cycle_diplomacy_events_pair_id', 'cycle_diplomacy_events', ['pair_id'])


def downgrade():
    op.drop_table('cycle_diplomacy_events')
    op.drop_table('cycle_diplomacy_proposals')
    op.drop_table('cycle_diplomacy_pairs')
