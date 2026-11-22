"""Добавляет сезоны кампании и неизменяемые результаты кланов.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""

from alembic import op
import sqlalchemy as sa


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "campaign_seasons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("starting_influence", sa.Integer(), server_default="100", nullable=False),
        sa.Column("reset_development", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("rules_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.UniqueConstraint("number"),
    )
    op.create_index("ix_campaign_seasons_number", "campaign_seasons", ["number"])
    op.create_index("ix_campaign_seasons_status", "campaign_seasons", ["status"])
    op.create_index("ix_campaign_seasons_starts_at", "campaign_seasons", ["starts_at"])
    op.create_index("ix_campaign_seasons_ends_at", "campaign_seasons", ["ends_at"])
    op.create_index(
        "uq_campaign_seasons_active",
        "campaign_seasons",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "campaign_season_clan_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("clan_id", sa.Integer(), nullable=True),
        sa.Column("clan_name", sa.String(length=160), nullable=False),
        sa.Column("clan_avatar_url", sa.String(), nullable=True),
        sa.Column("clan_map_color", sa.String(length=7), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("influence", sa.Integer(), server_default="0", nullable=False),
        sa.Column("base_influence", sa.Integer(), server_default="0", nullable=False),
        sa.Column("territory_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("wars_won", sa.Integer(), server_default="0", nullable=False),
        sa.Column("wars_lost", sa.Integer(), server_default="0", nullable=False),
        sa.Column("defenses_won", sa.Integer(), server_default="0", nullable=False),
        sa.Column("gold", sa.Integer(), server_default="0", nullable=False),
        sa.Column("iron", sa.Integer(), server_default="0", nullable=False),
        sa.Column("wood", sa.Integer(), server_default="0", nullable=False),
        sa.Column("food", sa.Integer(), server_default="0", nullable=False),
        sa.Column("mithril", sa.Integer(), server_default="0", nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["season_id"], ["campaign_seasons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clan_id"], ["clans.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("season_id", "clan_id", name="uq_campaign_season_clan"),
    )
    op.create_index("ix_campaign_season_clan_results_season_id", "campaign_season_clan_results", ["season_id"])
    op.create_index("ix_campaign_season_clan_results_clan_id", "campaign_season_clan_results", ["clan_id"])
    op.create_index("ix_campaign_season_result_rank", "campaign_season_clan_results", ["season_id", "rank"])


def downgrade():
    op.drop_index("ix_campaign_season_result_rank", table_name="campaign_season_clan_results")
    op.drop_index("ix_campaign_season_clan_results_clan_id", table_name="campaign_season_clan_results")
    op.drop_index("ix_campaign_season_clan_results_season_id", table_name="campaign_season_clan_results")
    op.drop_table("campaign_season_clan_results")
    op.drop_index("uq_campaign_seasons_active", table_name="campaign_seasons")
    op.drop_index("ix_campaign_seasons_ends_at", table_name="campaign_seasons")
    op.drop_index("ix_campaign_seasons_starts_at", table_name="campaign_seasons")
    op.drop_index("ix_campaign_seasons_status", table_name="campaign_seasons")
    op.drop_index("ix_campaign_seasons_number", table_name="campaign_seasons")
    op.drop_table("campaign_seasons")
