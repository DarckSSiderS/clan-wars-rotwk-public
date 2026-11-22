"""Persist explicitly saved season/clan defence templates, without backfill."""
from alembic import op
import sqlalchemy as sa

revision = 'r0f1g2h3i4j5'
down_revision = 'q9f0g1h2i3j4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cycle_defence_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('season_id', sa.Integer(), sa.ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('clan_id', sa.Integer(), sa.ForeignKey('clans.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('assignments', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.UniqueConstraint('season_id', 'clan_id', name='uq_cycle_defence_template_season_clan'),
        sa.CheckConstraint('revision > 0', name='ck_cycle_defence_template_revision'))


def downgrade():
    op.drop_table('cycle_defence_templates')
