"""Добавляет сохраняемые решения администратора по матчам войны.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""

from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "clan_war_match_results",
        sa.Column("admin_override", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "clan_war_match_results",
        sa.Column("admin_override_reason", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "clan_war_match_results",
        sa.Column("admin_override_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "clan_war_match_results",
        sa.Column("admin_override_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_war_match_override_user",
        "clan_war_match_results",
        "users",
        ["admin_override_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint(
        "fk_war_match_override_user",
        "clan_war_match_results",
        type_="foreignkey",
    )
    op.drop_column("clan_war_match_results", "admin_override_at")
    op.drop_column("clan_war_match_results", "admin_override_by_user_id")
    op.drop_column("clan_war_match_results", "admin_override_reason")
    op.drop_column("clan_war_match_results", "admin_override")
