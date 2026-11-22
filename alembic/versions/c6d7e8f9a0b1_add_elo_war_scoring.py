"""add Elo snapshots and clan patch preferences

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa


revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "clans",
        sa.Column(
            "preferred_patch",
            sa.String(length=20),
            nullable=False,
            server_default="all",
        ),
    )

    op.add_column("matches", sa.Column("winner_elo", sa.Float(), nullable=True))
    op.add_column("matches", sa.Column("loser_elo", sa.Float(), nullable=True))
    op.add_column(
        "matches",
        sa.Column("rating_patch_family", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "matches",
        sa.Column("ratings_captured_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "matches",
        sa.Column("rating_source", sa.String(length=40), nullable=True),
    )

    op.add_column(
        "clan_wars",
        sa.Column(
            "attacker_patch",
            sa.String(length=20),
            nullable=False,
            server_default="all",
        ),
    )
    op.add_column(
        "clan_wars",
        sa.Column("defender_patch", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "clan_wars",
        sa.Column(
            "scoring_version",
            sa.String(length=20),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.alter_column(
        "clan_wars",
        "scoring_version",
        server_default="elo_v1",
    )
    op.execute(
        "UPDATE clan_wars SET scoring_version = 'elo_v1' WHERE status = 'active'"
    )

    op.add_column(
        "clan_war_match_results",
        sa.Column("patch_family", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "clan_war_match_results",
        sa.Column("winner_rating", sa.Float(), nullable=True),
    )
    op.add_column(
        "clan_war_match_results",
        sa.Column("loser_rating", sa.Float(), nullable=True),
    )
    op.add_column(
        "clan_war_match_results",
        sa.Column("winner_expected_probability", sa.Float(), nullable=True),
    )
    op.add_column(
        "clan_war_match_results",
        sa.Column("loser_expected_probability", sa.Float(), nullable=True),
    )
    op.add_column(
        "clan_war_match_results",
        sa.Column(
            "scoring_version",
            sa.String(length=20),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.alter_column(
        "clan_war_match_results",
        "scoring_version",
        server_default="elo_v1",
    )


def downgrade():
    op.drop_column("clan_war_match_results", "scoring_version")
    op.drop_column("clan_war_match_results", "loser_expected_probability")
    op.drop_column("clan_war_match_results", "winner_expected_probability")
    op.drop_column("clan_war_match_results", "loser_rating")
    op.drop_column("clan_war_match_results", "winner_rating")
    op.drop_column("clan_war_match_results", "patch_family")
    op.drop_column("clan_wars", "scoring_version")
    op.drop_column("clan_wars", "defender_patch")
    op.drop_column("clan_wars", "attacker_patch")
    op.drop_column("matches", "rating_source")
    op.drop_column("matches", "ratings_captured_at")
    op.drop_column("matches", "rating_patch_family")
    op.drop_column("matches", "loser_elo")
    op.drop_column("matches", "winner_elo")
    op.drop_column("clans", "preferred_patch")
