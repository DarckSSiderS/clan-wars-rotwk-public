"""Seasonal wallets, relics, upgrades and frozen economic effects."""

from alembic import op
import sqlalchemy as sa

revision = 'g9v0w1x2y3z4'
down_revision = 'f8u9v0w1x2y3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cycle_economy_states',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('season_id', sa.Integer(), sa.ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('clan_id', sa.Integer(), sa.ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('wallet', sa.JSON(), nullable=False),
        sa.Column('relics', sa.JSON(), nullable=False),
        sa.Column('active_relics', sa.JSON(), nullable=False),
        sa.Column('starters_chosen', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
        sa.UniqueConstraint('season_id', 'clan_id', name='uq_cycle_economy_season_clan'),
        sa.CheckConstraint('revision > 0', name='ck_cycle_economy_revision'),
    )
    op.create_table(
        'cycle_territory_upgrades',
        sa.Column('season_id', sa.Integer(), sa.ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('territory_id', sa.Integer(), sa.ForeignKey('territories.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('levels', sa.JSON(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
        sa.CheckConstraint('revision > 0', name='ck_cycle_upgrade_revision'),
    )
    op.create_table(
        'cycle_economy_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('state_id', sa.Integer(), sa.ForeignKey('cycle_economy_states.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('effects', sa.JSON(), nullable=False),
        sa.Column('territory_upgrades', sa.JSON(), nullable=False),
        sa.Column('frozen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('state_revision', sa.Integer(), nullable=False),
        sa.UniqueConstraint('cycle_id', 'state_id', name='uq_cycle_economy_snapshot'),
    )


def downgrade():
    op.drop_table('cycle_economy_snapshots')
    op.drop_table('cycle_territory_upgrades')
    op.drop_table('cycle_economy_states')
