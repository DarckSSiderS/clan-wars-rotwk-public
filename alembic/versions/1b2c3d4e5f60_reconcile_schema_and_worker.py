"""reconcile runtime schema and add worker heartbeat

Revision ID: 1b2c3d4e5f60
Revises: 0f1c2d3e4a5b
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1b2c3d4e5f60"
down_revision: Union[str, None] = "0f1c2d3e4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _indexes(table_name: str) -> set[str]:
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
        if index.get("name")
    }


def _add_missing_columns(table_name: str, columns: list[sa.Column]) -> None:
    if table_name not in _table_names():
        return
    existing = _columns(table_name)
    for column in columns:
        if column.name not in existing:
            op.add_column(table_name, column)


def upgrade() -> None:
    if "clan_assets" not in _table_names():
        op.create_table(
            "clan_assets",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("key", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("bonus_type", sa.String(length=50), nullable=False),
            sa.Column("bonus_value", sa.Integer(), server_default="0", nullable=True),
            sa.Column("gold_cost", sa.Integer(), server_default="0", nullable=True),
            sa.Column("iron_cost", sa.Integer(), server_default="0", nullable=True),
            sa.Column("wood_cost", sa.Integer(), server_default="0", nullable=True),
            sa.Column("lava_cost", sa.Integer(), server_default="0", nullable=True),
            sa.Column("mithril_cost", sa.Integer(), server_default="0", nullable=True),
            sa.Column("is_unique", sa.Boolean(), server_default=sa.true(), nullable=True),
            sa.Column("is_available", sa.Boolean(), server_default=sa.true(), nullable=True),
            sa.Column("max_level", sa.Integer(), server_default="3", nullable=True),
            sa.Column("upgrade_multiplier", sa.Integer(), server_default="2", nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("key"),
        )
        op.create_index("ix_clan_assets_id", "clan_assets", ["id"])
        op.create_index("ix_clan_assets_key", "clan_assets", ["key"], unique=True)

    if "clan_owned_assets" not in _table_names():
        op.create_table(
            "clan_owned_assets",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("clan_id", sa.Integer(), nullable=False),
            sa.Column("asset_id", sa.Integer(), nullable=False),
            sa.Column("purchased_by", sa.Integer(), nullable=False),
            sa.Column(
                "purchased_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
            sa.Column("level", sa.Integer(), server_default="1", nullable=True),
            sa.ForeignKeyConstraint(["asset_id"], ["clan_assets.id"]),
            sa.ForeignKeyConstraint(["clan_id"], ["clans.id"]),
            sa.ForeignKeyConstraint(["purchased_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("clan_id", "asset_id", name="uq_clan_asset"),
        )
        op.create_index("ix_clan_owned_assets_id", "clan_owned_assets", ["id"])

    _add_missing_columns(
        "clan_wars",
        [
            sa.Column("winner_clan_id", sa.Integer(), nullable=True),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source_territory_id", sa.Integer(), nullable=True),
            sa.Column("attacker_power", sa.Integer(), server_default="0", nullable=True),
            sa.Column("defender_power", sa.Integer(), server_default="0", nullable=True),
            sa.Column("influence_cost", sa.Integer(), server_default="0", nullable=True),
        ],
    )
    if "clan_wars" in _table_names():
        indexes = _indexes("clan_wars")
        if "ix_war_attacking_clan" not in indexes:
            op.create_index("ix_war_attacking_clan", "clan_wars", ["attacking_clan_id"])
        if "ix_war_defending_clan" not in indexes:
            op.create_index("ix_war_defending_clan", "clan_wars", ["defending_clan_id"])

    _add_missing_columns(
        "clan_war_participants",
        [sa.Column("war_points", sa.Integer(), server_default="0", nullable=True)],
    )
    _add_missing_columns(
        "clans",
        [
            sa.Column("resources", sa.Integer(), server_default="500", nullable=True),
            sa.Column("territory_points", sa.Integer(), server_default="0", nullable=True),
            sa.Column("last_economy_tick", sa.DateTime(timezone=True), nullable=True),
            sa.Column("next_attack_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("gold", sa.Integer(), server_default="500", nullable=True),
            sa.Column("iron", sa.Integer(), server_default="10", nullable=True),
            sa.Column("wood", sa.Integer(), server_default="10", nullable=True),
            sa.Column("lava", sa.Integer(), server_default="5", nullable=True),
            sa.Column("mithril", sa.Integer(), server_default="2", nullable=True),
        ],
    )
    _add_missing_columns(
        "clan_members",
        [sa.Column("is_trader", sa.Boolean(), server_default=sa.false(), nullable=True)],
    )
    _add_missing_columns(
        "territories",
        [
            sa.Column("development_level", sa.Integer(), server_default="0", nullable=True),
            sa.Column("offense_level", sa.Integer(), server_default="0", nullable=True),
            sa.Column("adjacent_territory_ids", sa.JSON(), nullable=True),
            sa.Column("resource_type", sa.String(20), server_default="iron", nullable=True),
            sa.Column("resource_output", sa.Integer(), server_default="1", nullable=True),
            sa.Column("is_playable", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("is_coastal", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("has_port", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("required_territories", sa.Integer(), server_default="0", nullable=False),
            sa.Column("stronghold_power", sa.Integer(), server_default="0", nullable=False),
        ],
    )
    _add_missing_columns(
        "clan_assets",
        [
            sa.Column("max_level", sa.Integer(), server_default="3", nullable=True),
            sa.Column("upgrade_multiplier", sa.Integer(), server_default="2", nullable=True),
        ],
    )
    _add_missing_columns(
        "clan_owned_assets",
        [sa.Column("level", sa.Integer(), server_default="1", nullable=True)],
    )
    _add_missing_columns(
        "users",
        [
            sa.Column("role_id", sa.Integer(), nullable=True),
            sa.Column("is_claimed", sa.Boolean(), server_default=sa.true(), nullable=False),
        ],
    )
    _add_missing_columns(
        "shop_items",
        [
            sa.Column("slot", sa.String(), nullable=True),
            sa.Column("category", sa.String(), nullable=True),
            sa.Column("is_available", sa.Boolean(), server_default=sa.true(), nullable=True),
        ],
    )
    _add_missing_columns(
        "achievements",
        [
            sa.Column("target_value", sa.Integer(), server_default="1", nullable=True),
            sa.Column("reward_amount", sa.Integer(), server_default="0", nullable=True),
            sa.Column("achievement_type", sa.String(), nullable=True),
            sa.Column("is_available", sa.Boolean(), server_default=sa.true(), nullable=True),
        ],
    )
    _add_missing_columns(
        "user_achievements",
        [sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)],
    )

    if "worker_heartbeats" not in _table_names():
        op.create_table(
            "worker_heartbeats",
            sa.Column("worker_name", sa.String(length=80), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("last_duration_ms", sa.Integer(), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("worker_name"),
        )
        op.create_index(
            "ix_worker_heartbeats_heartbeat_at",
            "worker_heartbeats",
            ["heartbeat_at"],
        )


def downgrade() -> None:
    if "worker_heartbeats" in _table_names():
        if "ix_worker_heartbeats_heartbeat_at" in _indexes("worker_heartbeats"):
            op.drop_index(
                "ix_worker_heartbeats_heartbeat_at",
                table_name="worker_heartbeats",
            )
        op.drop_table("worker_heartbeats")
