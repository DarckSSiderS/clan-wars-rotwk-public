"""add territory required influence

Revision ID: 718293a4b5c6
Revises: 60718293a4b5
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision = "718293a4b5c6"
down_revision = "60718293a4b5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "territories",
        sa.Column(
            "required_influence",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
    )
    op.execute(
        """
        UPDATE territories
        SET required_influence = CEIL(
            CASE
                WHEN owner_clan_id IS NULL THEN 30
                ELSE 40
            END
            + COALESCE(strategic_value, 0) * 8
            + COALESCE(fortifications, 0) * 6
        )::integer
        """
    )


def downgrade():
    op.drop_column("territories", "required_influence")
