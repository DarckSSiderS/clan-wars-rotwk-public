"""Добавляет безопасное восстановление пароля.

Revision ID: m9b0c1d2e3f4
Revises: l8a9b0c1d2e3
Create Date: 2026-08-26 02:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "m9b0c1d2e3f4"
down_revision = "l8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "auth_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

    op.create_table(
        "password_recovery_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("created_ip", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_password_recovery_tokens_user_id", "password_recovery_tokens", ["user_id"])
    op.create_index("ix_password_recovery_tokens_email_hash", "password_recovery_tokens", ["email_hash"])
    op.create_index("ix_password_recovery_tokens_token_hash", "password_recovery_tokens", ["token_hash"])
    op.create_index("ix_password_recovery_tokens_created_ip", "password_recovery_tokens", ["created_ip"])
    op.create_index("ix_password_recovery_tokens_expires_at", "password_recovery_tokens", ["expires_at"])
    op.create_index("ix_password_recovery_tokens_created_at", "password_recovery_tokens", ["created_at"])
    op.create_index(
        "ix_password_recovery_rate_email",
        "password_recovery_tokens",
        ["email_hash", "created_at"],
    )
    op.create_index(
        "ix_password_recovery_rate_ip",
        "password_recovery_tokens",
        ["created_ip", "created_at"],
    )


def downgrade():
    op.drop_index("ix_password_recovery_rate_ip", table_name="password_recovery_tokens")
    op.drop_index("ix_password_recovery_rate_email", table_name="password_recovery_tokens")
    op.drop_index("ix_password_recovery_tokens_created_at", table_name="password_recovery_tokens")
    op.drop_index("ix_password_recovery_tokens_expires_at", table_name="password_recovery_tokens")
    op.drop_index("ix_password_recovery_tokens_created_ip", table_name="password_recovery_tokens")
    op.drop_index("ix_password_recovery_tokens_token_hash", table_name="password_recovery_tokens")
    op.drop_index("ix_password_recovery_tokens_email_hash", table_name="password_recovery_tokens")
    op.drop_index("ix_password_recovery_tokens_user_id", table_name="password_recovery_tokens")
    op.drop_table("password_recovery_tokens")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("auth_version")
