"""Add explicit active clan relic loadouts."""

from alembic import op
import sqlalchemy as sa


revision = "r4g5h6i7j8k9"
down_revision = "q3f4g5h6i7j8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("clans") as batch_op:
        batch_op.add_column(
            sa.Column("relic_loadout_locked_until", sa.DateTime(timezone=True), nullable=True)
        )
    with op.batch_alter_table("clan_owned_assets") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    op.execute(
        sa.text(
            """
            UPDATE clan_owned_assets
            SET is_active = true
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           row_number() OVER (
                               PARTITION BY clan_id
                               ORDER BY purchased_at, id
                           ) AS slot_number
                    FROM clan_owned_assets
                ) AS ranked_assets
                WHERE slot_number <= 4
            )
            """
        )
    )


def downgrade():
    with op.batch_alter_table("clan_owned_assets") as batch_op:
        batch_op.drop_column("is_active")
    with op.batch_alter_table("clans") as batch_op:
        batch_op.drop_column("relic_loadout_locked_until")
