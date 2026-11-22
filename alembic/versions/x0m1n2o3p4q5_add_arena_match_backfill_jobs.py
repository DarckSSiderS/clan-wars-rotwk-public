"""Add durable BFME Arena player match backfill jobs.

Revision ID: x0m1n2o3p4q5
Revises: w9l0m1n2o3p4
"""

from alembic import op
import sqlalchemy as sa


revision = "x0m1n2o3p4q5"
down_revision = "w9l0m1n2o3p4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "arena_match_backfill_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("identity_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("scanned_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["external_player_identities.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "identity_id",
            name="uq_arena_match_backfill_jobs_identity_id",
        ),
    )
    op.create_index(
        "ix_arena_match_backfill_jobs_identity_id",
        "arena_match_backfill_jobs",
        ["identity_id"],
    )
    op.create_index(
        "ix_arena_match_backfill_jobs_status",
        "arena_match_backfill_jobs",
        ["status"],
    )
    op.create_index(
        "ix_arena_match_backfill_jobs_next_attempt_at",
        "arena_match_backfill_jobs",
        ["next_attempt_at"],
    )
    op.create_index(
        "ix_arena_match_backfill_jobs_ready",
        "arena_match_backfill_jobs",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_arena_match_backfill_jobs_ready",
        table_name="arena_match_backfill_jobs",
    )
    op.drop_index(
        "ix_arena_match_backfill_jobs_next_attempt_at",
        table_name="arena_match_backfill_jobs",
    )
    op.drop_index(
        "ix_arena_match_backfill_jobs_status",
        table_name="arena_match_backfill_jobs",
    )
    op.drop_index(
        "ix_arena_match_backfill_jobs_identity_id",
        table_name="arena_match_backfill_jobs",
    )
    op.drop_table("arena_match_backfill_jobs")
