"""add gold income remainder

Revision ID: 8293a4b5c6d7
Revises: 718293a4b5c6
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision = "8293a4b5c6d7"
down_revision = "718293a4b5c6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "clans",
        sa.Column(
            "gold_income_remainder",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade():
    op.drop_column("clans", "gold_income_remainder")
