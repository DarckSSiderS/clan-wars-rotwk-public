"""Add campaign pause and worker alert state.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""

from alembic import op
import sqlalchemy as sa


revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "campaign_settings",
        sa.Column("is_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "campaign_settings",
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "campaign_settings",
        sa.Column("paused_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "campaign_settings",
        sa.Column("pause_reason", sa.String(length=500), nullable=True),
    )
    op.create_foreign_key(
        "fk_campaign_settings_paused_by_user",
        "campaign_settings",
        "users",
        ["paused_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "worker_heartbeats",
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "worker_heartbeats",
        sa.Column("last_notification_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("worker_heartbeats", "last_notification_at")
    op.drop_column("worker_heartbeats", "consecutive_failures")
    op.drop_constraint(
        "fk_campaign_settings_paused_by_user",
        "campaign_settings",
        type_="foreignkey",
    )
    op.drop_column("campaign_settings", "pause_reason")
    op.drop_column("campaign_settings", "paused_by_user_id")
    op.drop_column("campaign_settings", "paused_at")
    op.drop_column("campaign_settings", "is_paused")
