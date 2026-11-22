"""Добавляет отдельную эмблему клана для карты.

Revision ID: h4c5d6e7f8a9
Revises: g3b4c5d6e7f8
Create Date: 2026-08-11 19:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "h4c5d6e7f8a9"
down_revision = "g3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "clans",
        sa.Column("map_emblem_url", sa.String(), nullable=True),
    )


def downgrade():
    op.drop_column("clans", "map_emblem_url")
