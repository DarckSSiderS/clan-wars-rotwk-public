"""Reconcile territory names, stronghold roles, and naval progression."""

from alembic import op
import sqlalchemy as sa


revision = "s5h6i7j8k9l0"
down_revision = "r4g5h6i7j8k9"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE territories
            SET name = 'Келдуин',
                description = 'Келдуин — Бегущая река, связывающая Эребор, Дейл и земли у Моря Рун.'
            WHERE name IN ('Ford of Bruinen', 'Брод через Бруинен')
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE territories
            SET required_territories = 0,
                stronghold_power = 0,
                secondary_resource_type = NULL
            WHERE name IN ('Роковая Гора (Ородруин)', 'Роковая гора (Ородруин)')
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE territories
            SET resource_wealth = 220,
                influence_value = 160,
                required_influence = 500,
                required_territories = 6,
                stronghold_power = 4,
                resource_output = 1,
                secondary_resource_type = CASE
                    WHEN resource_type <> 'wood' THEN 'wood'
                    WHEN resource_type <> 'iron' THEN 'iron'
                    ELSE 'food'
                END
            WHERE name = 'Удун'
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE territories
            SET port_level = CASE
                    WHEN COALESCE(port_level, 0) >= COALESCE(fleet_level, 0)
                        THEN COALESCE(port_level, 0)
                    ELSE COALESCE(fleet_level, 0)
                END,
                fleet_level = CASE
                    WHEN COALESCE(port_level, 0) >= COALESCE(fleet_level, 0)
                        THEN COALESCE(port_level, 0)
                    ELSE COALESCE(fleet_level, 0)
                END
            WHERE has_port = true
            """
        )
    )


def downgrade():
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE territories
            SET name = 'Ford of Bruinen',
                description = 'Брод через Бруинен (Громовод) у Имладриса; место, где волны Эльронда смели Назгулов.'
            WHERE name = 'Келдуин'
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE territories
            SET required_territories = 6,
                stronghold_power = 4,
                secondary_resource_type = CASE
                    WHEN resource_type <> 'wood' THEN 'wood'
                    ELSE 'iron'
                END
            WHERE name IN ('Роковая Гора (Ородруин)', 'Роковая гора (Ородруин)')
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE territories
            SET required_territories = 0,
                stronghold_power = 0,
                secondary_resource_type = NULL
            WHERE name = 'Удун'
            """
        )
    )
