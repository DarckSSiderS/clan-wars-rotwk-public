"""add clan membership periods

Revision ID: 93a4b5c6d7e8
Revises: 8293a4b5c6d7
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision = "93a4b5c6d7e8"
down_revision = "8293a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "clan_membership_periods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("clan_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "started_reason",
            sa.String(length=40),
            nullable=False,
            server_default="joined",
        ),
        sa.Column("ended_reason", sa.String(length=40), nullable=True),
        sa.ForeignKeyConstraint(
            ["clan_id"],
            ["clans.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_clan_membership_periods_user_time",
        "clan_membership_periods",
        ["user_id", "started_at", "ended_at"],
    )
    op.create_index(
        "ix_clan_membership_periods_clan_time",
        "clan_membership_periods",
        ["clan_id", "started_at", "ended_at"],
    )

    op.execute(
        """
        INSERT INTO clan_membership_periods (
            user_id,
            clan_id,
            started_at,
            started_reason
        )
        SELECT
            user_id,
            clan_id,
            COALESCE(joined_at, CURRENT_TIMESTAMP),
            'migration_backfill'
        FROM clan_members
        """
    )
    op.create_index(
        "uq_clan_membership_periods_active_user",
        "clan_membership_periods",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
        sqlite_where=sa.text("ended_at IS NULL"),
    )


def downgrade():
    op.drop_index(
        "uq_clan_membership_periods_active_user",
        table_name="clan_membership_periods",
    )
    op.drop_index(
        "ix_clan_membership_periods_clan_time",
        table_name="clan_membership_periods",
    )
    op.drop_index(
        "ix_clan_membership_periods_user_time",
        table_name="clan_membership_periods",
    )
    op.drop_table("clan_membership_periods")
