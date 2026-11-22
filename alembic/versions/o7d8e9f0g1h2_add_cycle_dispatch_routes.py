"""Снимки географии подкреплений отдельно от состояния игровых правил."""
from alembic import op
import sqlalchemy as sa

revision = 'o7d8e9f0g1h2'
down_revision = 'n6c7d8e9f0g1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cycle_dispatch_routes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('campaign_cycles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('dispatch_id', sa.String(120), nullable=False),
        sa.Column('origin_territory_id', sa.Integer()),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.UniqueConstraint('cycle_id', 'dispatch_id', name='uq_cycle_dispatch_route'))
    op.create_index('ix_cycle_dispatch_routes_cycle_id', 'cycle_dispatch_routes', ['cycle_id'])


def downgrade():
    op.drop_index('ix_cycle_dispatch_routes_cycle_id', table_name='cycle_dispatch_routes')
    op.drop_table('cycle_dispatch_routes')
