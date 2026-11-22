"""Auditable, idempotent ownership corrections for cycle battles."""

from alembic import op
import sqlalchemy as sa


revision = 'l4a5b6c7d8e9'
down_revision = 'k3z4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cycle_ownership_corrections',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('season_id', sa.Integer(), sa.ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('battle_id', sa.Integer(), sa.ForeignKey('cycle_territory_battles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('current_cycle_id', sa.Integer(), sa.ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('territory_id', sa.Integer(), sa.ForeignKey('territories.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('previous_owner_clan_id', sa.Integer(), sa.ForeignKey('clans.id', ondelete='SET NULL')),
        sa.Column('new_owner_clan_id', sa.Integer(), sa.ForeignKey('clans.id', ondelete='SET NULL')),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('command_id', sa.String(120), nullable=False),
        sa.Column('preview_token', sa.String(64), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('applied_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('season_id', 'command_id', name='uq_cycle_ownership_command'))
    op.create_index('ix_cycle_ownership_corrections_battle_id', 'cycle_ownership_corrections', ['battle_id'])


def downgrade():
    op.drop_index('ix_cycle_ownership_corrections_battle_id', table_name='cycle_ownership_corrections')
    op.drop_table('cycle_ownership_corrections')
