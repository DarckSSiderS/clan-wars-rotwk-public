"""Выбор земель и стартовых артефактов до ручного запуска сезона."""
from alembic import op
import sqlalchemy as sa

revision = 'u3i4j5k6l7m8'
down_revision = 't2h3i4j5k6l7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('campaign_preseason_candidates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('preparation_id', sa.Integer(), sa.ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('clan_id', sa.Integer(), nullable=False),
        sa.Column('qualified_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('selected_four', sa.JSON(), nullable=False))
    op.create_index('ix_campaign_preseason_candidates_preparation_id', 'campaign_preseason_candidates', ['preparation_id'])
    op.create_table('campaign_preseasons',
        sa.Column('source_season_id', sa.Integer(), sa.ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('source_archive_checksum', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('initial_owners', sa.JSON(), nullable=False),
        sa.Column('qualifications', sa.JSON(), nullable=False),
        sa.Column('launched_season_id', sa.Integer(), sa.ForeignKey('campaign_seasons.id', ondelete='RESTRICT')))
    op.create_table('campaign_preseason_choices',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('preparation_id', sa.Integer(), sa.ForeignKey('campaign_preseasons.source_season_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('clan_id', sa.Integer(), sa.ForeignKey('clans.id', ondelete='SET NULL')),
        sa.Column('selected_lands', sa.JSON(), nullable=False),
        sa.Column('selected_relics', sa.JSON(), nullable=False),
        sa.Column('lands_chosen_at', sa.DateTime(timezone=True)),
        sa.Column('relics_chosen_at', sa.DateTime(timezone=True)),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.UniqueConstraint('preparation_id', 'clan_id', name='uq_preseason_choice_clan'))


def downgrade():
    op.drop_table('campaign_preseason_choices')
    op.drop_table('campaign_preseasons')
    op.drop_index('ix_campaign_preseason_candidates_preparation_id', table_name='campaign_preseason_candidates')
    op.drop_table('campaign_preseason_candidates')
