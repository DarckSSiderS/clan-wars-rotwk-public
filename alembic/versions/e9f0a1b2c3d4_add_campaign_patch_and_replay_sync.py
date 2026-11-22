"""Add campaign patch settings and replay sync states.

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
"""

from alembic import op
import sqlalchemy as sa


revision = "e9f0a1b2c3d4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "campaign_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "patch_202_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "ennorath_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("updated_by", sa.String(length=100), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        INSERT INTO campaign_settings
            (id, patch_202_enabled, ennorath_enabled)
        VALUES (1, TRUE, TRUE)
        """
    )

    op.create_table(
        "replay_sync_states",
        sa.Column("replay_id", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("patch_family", sa.String(length=20), nullable=True),
        sa.Column("patch_name", sa.String(length=160), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("replay_id"),
    )
    op.create_index(
        "ix_replay_sync_states_status",
        "replay_sync_states",
        ["status"],
    )
    op.create_index(
        "ix_replay_sync_states_patch_family",
        "replay_sync_states",
        ["patch_family"],
    )
    op.create_index(
        "ix_replay_sync_states_last_attempt_at",
        "replay_sync_states",
        ["last_attempt_at"],
    )


def downgrade():
    op.drop_index(
        "ix_replay_sync_states_last_attempt_at",
        table_name="replay_sync_states",
    )
    op.drop_index(
        "ix_replay_sync_states_patch_family",
        table_name="replay_sync_states",
    )
    op.drop_index(
        "ix_replay_sync_states_status",
        table_name="replay_sync_states",
    )
    op.drop_table("replay_sync_states")
    op.drop_table("campaign_settings")
