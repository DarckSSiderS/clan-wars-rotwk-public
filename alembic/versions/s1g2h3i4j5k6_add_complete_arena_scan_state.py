"""Хранит границы полного обхода отдельно от сигнала фонового процесса."""

from alembic import op
import sqlalchemy as sa


revision = 's1g2h3i4j5k6'
down_revision = 'r0f1g2h3i4j5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cycle_arena_scan_state',
        sa.Column('source', sa.String(40), primary_key=True),
        sa.Column('covered_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('covered_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('replays_count', sa.Integer(), nullable=False))


def downgrade():
    op.drop_table('cycle_arena_scan_state')
