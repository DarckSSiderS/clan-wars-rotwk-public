"""add permanent territory influence

Revision ID: 60718293a4b5
Revises: 5f60718293a4
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision = "60718293a4b5"
down_revision = "5f60718293a4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "clans",
        sa.Column(
            "base_influence",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("100"),
        ),
    )
    op.add_column(
        "territories",
        sa.Column(
            "influence_value",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.execute(
        """
        UPDATE territories
        SET influence_value = GREATEST(
            1,
            FLOOR(
                COALESCE(resource_wealth, 0)
                + COALESCE(strategic_value, 0) * 10
                + COALESCE(population, 0) / 1000.0
                + COALESCE(development_level, 0) * 15
                + COALESCE(stronghold_power, 0) * 40
            )::integer
        )
        """
    )
    op.execute(
        """
        UPDATE clans
        SET base_influence = COALESCE(territory_points, 0)
        """
    )
    op.execute(
        """
        UPDATE clans AS clan
        SET territory_points = clan.base_influence + COALESCE(
            (
                SELECT SUM(territory.influence_value)
                FROM territories AS territory
                WHERE territory.owner_clan_id = clan.id
            ),
            0
        )
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE clans
        SET territory_points = base_influence
        """
    )
    op.drop_column("territories", "influence_value")
    op.drop_column("clans", "base_influence")
