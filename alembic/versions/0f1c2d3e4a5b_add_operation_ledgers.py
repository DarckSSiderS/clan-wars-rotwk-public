"""add resource and admin operation ledgers

Revision ID: 0f1c2d3e4a5b
Revises: f3b2d7a91c40
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0f1c2d3e4a5b"
down_revision: Union[str, None] = "f3b2d7a91c40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resource_ledger",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.String(length=120), nullable=False),
        sa.Column("clan_id", sa.Integer(), nullable=False),
        sa.Column("resource", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_before", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=True),
        sa.Column("source_id", sa.String(length=120), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["clan_id"], ["clans.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operation_id",
            "clan_id",
            "resource",
            name="uq_resource_ledger_operation_clan_resource",
        ),
    )
    op.create_index("ix_resource_ledger_id", "resource_ledger", ["id"])
    op.create_index("ix_resource_ledger_operation_id", "resource_ledger", ["operation_id"])
    op.create_index("ix_resource_ledger_clan_id", "resource_ledger", ["clan_id"])
    op.create_index("ix_resource_ledger_action", "resource_ledger", ["action"])

    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column("before_data", sa.JSON(), nullable=True),
        sa.Column("after_data", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_audit_log_id", "admin_audit_log", ["id"])
    op.create_index("ix_admin_audit_log_actor_user_id", "admin_audit_log", ["actor_user_id"])
    op.create_index("ix_admin_audit_log_action", "admin_audit_log", ["action"])
    op.create_index("ix_admin_audit_log_entity_type", "admin_audit_log", ["entity_type"])
    op.create_index("ix_admin_audit_log_entity_id", "admin_audit_log", ["entity_id"])


def downgrade() -> None:
    for index_name in (
        "ix_admin_audit_log_entity_id",
        "ix_admin_audit_log_entity_type",
        "ix_admin_audit_log_action",
        "ix_admin_audit_log_actor_user_id",
        "ix_admin_audit_log_id",
    ):
        op.drop_index(index_name, table_name="admin_audit_log")
    op.drop_table("admin_audit_log")

    for index_name in (
        "ix_resource_ledger_action",
        "ix_resource_ledger_clan_id",
        "ix_resource_ledger_operation_id",
        "ix_resource_ledger_id",
    ):
        op.drop_index(index_name, table_name="resource_ledger")
    op.drop_table("resource_ledger")
