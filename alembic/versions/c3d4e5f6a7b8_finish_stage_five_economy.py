"""Завершить пятый этап экономики и реликвий.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""

from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("clans") as batch_op:
        batch_op.alter_column("lava", new_column_name="food")

    with op.batch_alter_table("clan_assets") as batch_op:
        batch_op.alter_column("lava_cost", new_column_name="food_cost")
        batch_op.add_column(
            sa.Column(
                "required_influence_level_1",
                sa.Integer(),
                nullable=False,
                server_default="250",
            )
        )
        batch_op.add_column(
            sa.Column(
                "required_influence_level_2",
                sa.Integer(),
                nullable=False,
                server_default="750",
            )
        )
        batch_op.add_column(
            sa.Column(
                "required_influence_level_3",
                sa.Integer(),
                nullable=False,
                server_default="1500",
            )
        )

    with op.batch_alter_table("territories") as batch_op:
        batch_op.add_column(
            sa.Column(
                "secondary_resource_type",
                sa.String(length=20),
                nullable=True,
            )
        )

    connection = op.get_bind()
    for table, column in (
        ("territories", "resource_type"),
        ("market_offers", "give_resource"),
        ("market_offers", "receive_resource"),
        ("trade_caravans", "resource"),
        ("resource_ledger", "resource"),
    ):
        connection.execute(
            sa.text(
                f"UPDATE {table} SET {column} = 'food' "
                f"WHERE {column} = 'lava'"
            )
        )

    connection.execute(
        sa.text(
            """
            UPDATE territories
            SET secondary_resource_type = CASE resource_type
                WHEN 'iron' THEN 'wood'
                WHEN 'wood' THEN 'food'
                WHEN 'food' THEN 'iron'
                WHEN 'mithril' THEN 'iron'
                ELSE 'iron'
            END
            WHERE COALESCE(stronghold_power, 0) > 0
              AND secondary_resource_type IS NULL
            """
        )
    )


def downgrade():
    connection = op.get_bind()
    for table, column in (
        ("territories", "resource_type"),
        ("market_offers", "give_resource"),
        ("market_offers", "receive_resource"),
        ("trade_caravans", "resource"),
        ("resource_ledger", "resource"),
    ):
        connection.execute(
            sa.text(
                f"UPDATE {table} SET {column} = 'lava' "
                f"WHERE {column} = 'food'"
            )
        )

    with op.batch_alter_table("territories") as batch_op:
        batch_op.drop_column("secondary_resource_type")

    with op.batch_alter_table("clan_assets") as batch_op:
        batch_op.drop_column("required_influence_level_3")
        batch_op.drop_column("required_influence_level_2")
        batch_op.drop_column("required_influence_level_1")
        batch_op.alter_column("food_cost", new_column_name="lava_cost")

    with op.batch_alter_table("clans") as batch_op:
        batch_op.alter_column("food", new_column_name="lava")
