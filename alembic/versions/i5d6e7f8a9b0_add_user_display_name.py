"""Добавляет отдельный публичный ник пользователя.

Revision ID: i5d6e7f8a9b0
Revises: h4c5d6e7f8a9
Create Date: 2026-08-12 17:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "i5d6e7f8a9b0"
down_revision = "h4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("display_name", sa.String(length=120), nullable=True),
    )
    op.create_index("ix_users_display_name", "users", ["display_name"], unique=False)


def downgrade():
    op.drop_index("ix_users_display_name", table_name="users")
    op.drop_column("users", "display_name")
