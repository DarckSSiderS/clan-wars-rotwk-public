"""add war match results

Revision ID: a4b5c6d7e8f9
Revises: 93a4b5c6d7e8
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision = "a4b5c6d7e8f9"
down_revision = "93a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "clan_war_match_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("war_id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("played_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("winner_user_id", sa.Integer(), nullable=False),
        sa.Column("loser_user_id", sa.Integer(), nullable=False),
        sa.Column("winner_clan_id", sa.Integer(), nullable=False),
        sa.Column("loser_clan_id", sa.Integer(), nullable=False),
        sa.Column("winner_base_points", sa.Float(), nullable=False),
        sa.Column("winner_power_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("winner_power_bonus_points", sa.Float(), nullable=False, server_default="0"),
        sa.Column("winner_relic_bonus_points", sa.Float(), nullable=False, server_default="0"),
        sa.Column("winner_total_points", sa.Float(), nullable=False),
        sa.Column("loser_base_points", sa.Float(), nullable=False),
        sa.Column("loser_power_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loser_power_bonus_points", sa.Float(), nullable=False, server_default="0"),
        sa.Column("loser_relic_bonus_points", sa.Float(), nullable=False, server_default="0"),
        sa.Column("loser_total_points", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["loser_clan_id"], ["clans.id"]),
        sa.ForeignKeyConstraint(["loser_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"]),
        sa.ForeignKeyConstraint(
            ["war_id"],
            ["clan_wars.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["winner_clan_id"], ["clans.id"]),
        sa.ForeignKeyConstraint(["winner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("war_id", "match_id", name="uq_war_match_result"),
    )
    op.create_index(
        "ix_war_match_results_war_played",
        "clan_war_match_results",
        ["war_id", "played_at"],
    )
    op.create_index(
        "ix_war_match_results_match",
        "clan_war_match_results",
        ["match_id"],
    )


def downgrade():
    op.drop_index(
        "ix_war_match_results_match",
        table_name="clan_war_match_results",
    )
    op.drop_index(
        "ix_war_match_results_war_played",
        table_name="clan_war_match_results",
    )
    op.drop_table("clan_war_match_results")
