"""Opt-in new-season cycles and private clan plans."""

from alembic import op
import sqlalchemy as sa

revision = 'e7t8u9v0w1x2'
down_revision = 'd6s7t8u9v0w1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'campaign_cycles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('season_id', sa.Integer(), sa.ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('rule_version', sa.Integer(), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('preparation_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('settled_at', sa.DateTime(timezone=True)),
        sa.Column('import_verified_at', sa.DateTime(timezone=True)),
        sa.Column('season_end_requested', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('dependencies', sa.JSON(), nullable=False),
        sa.Column('planning_snapshot', sa.JSON()),
        sa.Column('orders_frozen_at', sa.DateTime(timezone=True)),
        sa.Column('battles_registered', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
        sa.UniqueConstraint('season_id', 'number', name='uq_campaign_cycle_number'),
        sa.CheckConstraint('number > 0 AND rule_version > 0 AND revision > 0', name='ck_campaign_cycle_positive'),
    )
    op.create_index('ix_campaign_cycles_season_id', 'campaign_cycles', ['season_id'])
    op.create_table(
        'campaign_cycle_plans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('clan_id', sa.Integer(), sa.ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('orders', sa.JSON(), nullable=False),
        sa.Column('snapshot', sa.JSON()),
        sa.Column('frozen_at', sa.DateTime(timezone=True)),
        sa.Column('updated_by_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.UniqueConstraint('cycle_id', 'clan_id', name='uq_campaign_cycle_clan_plan'),
        sa.CheckConstraint('revision > 0', name='ck_campaign_cycle_plan_revision'),
    )
    op.create_index('ix_campaign_cycle_plans_cycle_id', 'campaign_cycle_plans', ['cycle_id'])
    op.create_index('ix_campaign_cycle_plans_clan_id', 'campaign_cycle_plans', ['clan_id'])


def downgrade():
    op.drop_table('campaign_cycle_plans')
    op.drop_table('campaign_cycles')
