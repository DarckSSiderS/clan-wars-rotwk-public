"""Independent interception matches and verified import windows."""

from alembic import op
import sqlalchemy as sa

revision = 'm5b6c7d8e9f0'
down_revision = 'l4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cycle_interceptions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('dispatch_id', sa.String(120), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('verified_revision', sa.Integer()),
        sa.Column('verified_at', sa.DateTime(timezone=True)),
        sa.Column('source_cursor', sa.String(500)),
        sa.Column('covered_start', sa.DateTime(timezone=True)),
        sa.Column('covered_end', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('cycle_id', 'dispatch_id', name='uq_cycle_interception_dispatch'))
    op.create_index('ix_cycle_interceptions_cycle_id', 'cycle_interceptions', ['cycle_id'])
    op.create_table('cycle_interception_contributions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('interception_id', sa.Integer(), sa.ForeignKey('cycle_interceptions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('replay_id', sa.String(120), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('side_clan_id', sa.Integer(), nullable=False),
        sa.Column('points', sa.Numeric(28, 12), nullable=False),
        sa.Column('counted', sa.Boolean(), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('calculation', sa.JSON(), nullable=False),
        sa.UniqueConstraint('interception_id', 'replay_id', 'user_id', name='uq_interception_match_player'))
    op.create_index('ix_cycle_interception_contributions_interception_id', 'cycle_interception_contributions', ['interception_id'])


def downgrade():
    op.drop_index('ix_cycle_interception_contributions_interception_id', table_name='cycle_interception_contributions')
    op.drop_table('cycle_interception_contributions')
    op.drop_index('ix_cycle_interceptions_cycle_id', table_name='cycle_interceptions')
    op.drop_table('cycle_interceptions')
