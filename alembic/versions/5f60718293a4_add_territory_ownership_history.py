"""add territory ownership history and weekly payout clocks

Revision ID: 5f60718293a4
Revises: 4e5f60718293
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision = "5f60718293a4"
down_revision = "4e5f60718293"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "territories",
        "strategic_value",
        existing_type=sa.Integer(),
        type_=sa.Float(),
        existing_nullable=True,
        existing_server_default=sa.text("1"),
        server_default=sa.text("0"),
        postgresql_using="strategic_value::double precision",
    )
    op.add_column(
        "territories",
        sa.Column("owned_since", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "territories",
        sa.Column("last_weekly_payout_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "territory_ownership_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("territory_id", sa.Integer(), nullable=False),
        sa.Column("clan_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("war_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=40), nullable=False, server_default="capture"),
        sa.ForeignKeyConstraint(["territory_id"], ["territories.id"]),
        sa.ForeignKeyConstraint(["clan_id"], ["clans.id"]),
        sa.ForeignKeyConstraint(
            ["war_id"],
            ["clan_wars.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_territory_ownership_history_territory_id",
        "territory_ownership_history",
        ["territory_id"],
    )
    op.create_index(
        "ix_territory_ownership_history_clan_id",
        "territory_ownership_history",
        ["clan_id"],
    )
    op.create_index(
        "ix_territory_ownership_history_started_at",
        "territory_ownership_history",
        ["started_at"],
    )
    op.create_index(
        "ix_territory_ownership_history_ended_at",
        "territory_ownership_history",
        ["ended_at"],
    )
    op.create_index(
        "ix_territory_ownership_history_war_id",
        "territory_ownership_history",
        ["war_id"],
    )

    op.execute(
        """
        UPDATE territories
        SET owned_since = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP),
            last_weekly_payout_at = CURRENT_TIMESTAMP
        WHERE owner_clan_id IS NOT NULL
        """
    )
    op.execute(
        """
        INSERT INTO territory_ownership_history
            (territory_id, clan_id, started_at, reason)
        SELECT id, owner_clan_id, owned_since, 'migration'
        FROM territories
        WHERE owner_clan_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE territories
        SET strategic_value = ROUND(
            (
                COALESCE(development_level, 0)
                + COALESCE(fortifications, 0)
                + COALESCE(offense_level, 0)
                + CASE WHEN has_port THEN COALESCE(port_level, 0) ELSE 0 END
                + CASE WHEN has_port THEN COALESCE(fleet_level, 0) ELSE 0 END
            )::numeric
            / CASE WHEN has_port THEN 5 ELSE 3 END,
            1
        )
        """
    )


def downgrade():
    op.drop_index(
        "ix_territory_ownership_history_war_id",
        table_name="territory_ownership_history",
    )
    op.drop_index(
        "ix_territory_ownership_history_ended_at",
        table_name="territory_ownership_history",
    )
    op.drop_index(
        "ix_territory_ownership_history_started_at",
        table_name="territory_ownership_history",
    )
    op.drop_index(
        "ix_territory_ownership_history_clan_id",
        table_name="territory_ownership_history",
    )
    op.drop_index(
        "ix_territory_ownership_history_territory_id",
        table_name="territory_ownership_history",
    )
    op.drop_table("territory_ownership_history")
    op.drop_column("territories", "last_weekly_payout_at")
    op.drop_column("territories", "owned_since")
    op.alter_column(
        "territories",
        "strategic_value",
        existing_type=sa.Float(),
        type_=sa.Integer(),
        existing_nullable=True,
        server_default=sa.text("1"),
        postgresql_using="round(strategic_value)::integer",
    )
