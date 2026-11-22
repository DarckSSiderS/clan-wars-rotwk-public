"""Private scouting requests and immutable saved-order history."""

from alembic import op
import sqlalchemy as sa

revision = 'i1x2y3z4a5b6'
down_revision = 'h0w1x2y3z4a5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'campaign_cycle_plan_revisions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('campaign_cycle_plans.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('saved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('orders', sa.JSON(), nullable=False),
        sa.UniqueConstraint('plan_id', 'revision', name='uq_cycle_plan_revision_history'),
    )
    op.create_index('ix_campaign_cycle_plan_revisions_plan_id', 'campaign_cycle_plan_revisions', ['plan_id'])
    op.create_table(
        'cycle_scout_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('clan_id', sa.Integer(), sa.ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('territory_id', sa.Integer(), sa.ForeignKey('territories.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('report', sa.JSON()),
        sa.UniqueConstraint('cycle_id', 'clan_id', name='uq_cycle_scout_clan'),
    )


def downgrade():
    op.drop_table('cycle_scout_requests')
    op.drop_table('campaign_cycle_plan_revisions')
