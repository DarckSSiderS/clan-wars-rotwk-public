"""Аудит пересмотра перехватов и отдельные ручные поправки."""

from alembic import op
import sqlalchemy as sa

revision = 'n6c7d8e9f0g1'
down_revision = 'm5b6c7d8e9f0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('cycle_interceptions', sa.Column('original_applied_result', sa.JSON(), nullable=True))
    op.add_column('cycle_interception_contributions', sa.Column('review_counted', sa.Boolean(), nullable=True))
    op.create_table('cycle_interception_review_commands',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('interception_id', sa.Integer(), sa.ForeignKey('cycle_interceptions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('command_id', sa.String(120), nullable=False),
        sa.Column('action', sa.String(40), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('expected_revision', sa.Integer(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('before', sa.JSON(), nullable=False),
        sa.Column('after', sa.JSON(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('interception_id', 'command_id', name='uq_interception_review_command'))
    op.create_index('ix_cycle_interception_review_commands_interception_id', 'cycle_interception_review_commands', ['interception_id'])
    op.create_table('cycle_interception_adjustments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('interception_id', sa.Integer(), sa.ForeignKey('cycle_interceptions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('command_id', sa.String(120), nullable=False),
        sa.Column('side_clan_id', sa.Integer(), nullable=False),
        sa.Column('points', sa.Numeric(28, 12), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('interception_id', 'command_id', name='uq_interception_adjustment_command'))
    op.create_index('ix_cycle_interception_adjustments_interception_id', 'cycle_interception_adjustments', ['interception_id'])


def downgrade():
    op.drop_index('ix_cycle_interception_adjustments_interception_id', table_name='cycle_interception_adjustments')
    op.drop_table('cycle_interception_adjustments')
    op.drop_index('ix_cycle_interception_review_commands_interception_id', table_name='cycle_interception_review_commands')
    op.drop_table('cycle_interception_review_commands')
    with op.batch_alter_table('cycle_interception_contributions') as batch:
        batch.drop_column('review_counted')
    with op.batch_alter_table('cycle_interceptions') as batch:
        batch.drop_column('original_applied_result')
