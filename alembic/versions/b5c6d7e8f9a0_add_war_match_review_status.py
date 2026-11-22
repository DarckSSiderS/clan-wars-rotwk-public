"""add war match review status

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "clan_war_match_results",
        "winner_clan_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "clan_war_match_results",
        "loser_clan_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.add_column(
        "clan_war_match_results",
        sa.Column(
            "is_counted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "clan_war_match_results",
        sa.Column("rejection_reason", sa.String(length=120), nullable=True),
    )


def downgrade():
    op.drop_column("clan_war_match_results", "rejection_reason")
    op.drop_column("clan_war_match_results", "is_counted")
    op.alter_column(
        "clan_war_match_results",
        "loser_clan_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "clan_war_match_results",
        "winner_clan_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
