"""Multi-side territory battles and personal accounting for cycle seasons."""

from alembic import op
import sqlalchemy as sa

revision = 'f8u9v0w1x2y3'
down_revision = 'e7t8u9v0w1x2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cycle_territory_battles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('territory_id', sa.Integer(), sa.ForeignKey('territories.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('owner_clan_id', sa.Integer(), sa.ForeignKey('clans.id', ondelete='SET NULL')),
        sa.Column('winner_clan_id', sa.Integer(), sa.ForeignKey('clans.id', ondelete='SET NULL')),
        sa.Column('recalculated_winner_clan_id', sa.Integer(), sa.ForeignKey('clans.id', ondelete='SET NULL')),
        sa.Column('sides', sa.JSON(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('ownership_applied_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('cycle_id', 'territory_id', name='uq_cycle_territory_battle'),
    )
    op.create_index('ix_cycle_territory_battles_cycle_id', 'cycle_territory_battles', ['cycle_id'])
    op.create_table(
        'cycle_match_contributions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('battle_id', sa.Integer(), sa.ForeignKey('cycle_territory_battles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('replay_id', sa.String(120), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('clan_id', sa.Integer(), sa.ForeignKey('clans.id', ondelete='SET NULL')),
        sa.Column('points', sa.Numeric(28, 12), nullable=False),
        sa.Column('counted', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('calculation', sa.JSON()),
        sa.Column('review_reason', sa.String(500)),
        sa.Column('reviewed_by_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.UniqueConstraint('battle_id', 'replay_id', 'user_id', name='uq_cycle_match_player'),
    )
    op.create_index('ix_cycle_match_contributions_battle_id', 'cycle_match_contributions', ['battle_id'])
    op.create_table(
        'cycle_score_adjustments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('battle_id', sa.Integer(), sa.ForeignKey('cycle_territory_battles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('clan_id', sa.Integer(), sa.ForeignKey('clans.id', ondelete='SET NULL')),
        sa.Column('command_id', sa.String(120), nullable=False),
        sa.Column('points', sa.Numeric(28, 12), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.UniqueConstraint('battle_id', 'command_id', name='uq_cycle_adjustment_command'),
    )
    op.create_index('ix_cycle_score_adjustments_battle_id', 'cycle_score_adjustments', ['battle_id'])


def downgrade():
    op.drop_table('cycle_score_adjustments')
    op.drop_table('cycle_match_contributions')
    op.drop_table('cycle_territory_battles')
