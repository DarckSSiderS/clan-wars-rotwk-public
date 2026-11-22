"""Хранит явные решения администратора по поздним реплеям."""

from alembic import op
import sqlalchemy as sa

revision = 'p8e9f0g1h2i3'
down_revision = 'o7d8e9f0g1h2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cycle_late_replay_decisions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('battle_id', sa.Integer(), sa.ForeignKey('cycle_territory_battles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('match_id', sa.Integer(), sa.ForeignKey('matches.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('command_id', sa.String(120), nullable=False),
        sa.Column('preview_token', sa.String(64), nullable=False),
        sa.Column('counted', sa.Boolean(), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_ids', sa.JSON(), nullable=False),
        sa.UniqueConstraint('battle_id', 'command_id', name='uq_cycle_late_replay_command'))
    op.create_index('ix_cycle_late_replay_decisions_battle_id', 'cycle_late_replay_decisions', ['battle_id'])


def downgrade():
    op.drop_index('ix_cycle_late_replay_decisions_battle_id', table_name='cycle_late_replay_decisions')
    op.drop_table('cycle_late_replay_decisions')
