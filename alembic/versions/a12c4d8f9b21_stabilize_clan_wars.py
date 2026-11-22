"""stabilize clan wars

Revision ID: a12c4d8f9b21
Revises: 811e4000a78a
Create Date: 2026-05-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "a12c4d8f9b21"
down_revision: Union[str, None] = "811e4000a78a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column["name"] for column in inspect(bind).get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {index["name"] for index in inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    columns = _columns("clan_wars")
    if "winner_clan_id" not in columns:
        op.add_column("clan_wars", sa.Column("winner_clan_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_clan_wars_winner_clan_id_clans",
            "clan_wars",
            "clans",
            ["winner_clan_id"],
            ["id"],
        )
    if "ended_at" not in columns:
        op.add_column("clan_wars", sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True))
    if "updated_at" not in columns:
        op.add_column("clan_wars", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))

    indexes = _indexes("clan_wars")
    if "ix_war_attacking_clan" not in indexes:
        op.create_index("ix_war_attacking_clan", "clan_wars", ["attacking_clan_id"])
    if "ix_war_defending_clan" not in indexes:
        op.create_index("ix_war_defending_clan", "clan_wars", ["defending_clan_id"])

    shop_columns = _columns("shop_items")
    if "slot" not in shop_columns:
        op.add_column("shop_items", sa.Column("slot", sa.String(), nullable=True))
    if "category" not in shop_columns:
        op.add_column("shop_items", sa.Column("category", sa.String(), nullable=True))
    if "is_available" not in shop_columns:
        op.add_column("shop_items", sa.Column("is_available", sa.Boolean(), server_default=sa.true(), nullable=True))

    achievement_columns = _columns("achievements")
    if "target_value" not in achievement_columns:
        op.add_column("achievements", sa.Column("target_value", sa.Integer(), server_default="1", nullable=True))
    if "reward_amount" not in achievement_columns:
        op.add_column("achievements", sa.Column("reward_amount", sa.Integer(), server_default="0", nullable=True))
    if "achievement_type" not in achievement_columns:
        op.add_column("achievements", sa.Column("achievement_type", sa.String(), nullable=True))
    if "is_available" not in achievement_columns:
        op.add_column("achievements", sa.Column("is_available", sa.Boolean(), server_default=sa.true(), nullable=True))

    user_achievement_columns = _columns("user_achievements")
    if "updated_at" not in user_achievement_columns:
        op.add_column("user_achievements", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    user_achievement_columns = _columns("user_achievements")
    if "updated_at" in user_achievement_columns:
        op.drop_column("user_achievements", "updated_at")

    achievement_columns = _columns("achievements")
    if "is_available" in achievement_columns:
        op.drop_column("achievements", "is_available")
    if "achievement_type" in achievement_columns:
        op.drop_column("achievements", "achievement_type")
    if "reward_amount" in achievement_columns:
        op.drop_column("achievements", "reward_amount")
    if "target_value" in achievement_columns:
        op.drop_column("achievements", "target_value")

    shop_columns = _columns("shop_items")
    if "is_available" in shop_columns:
        op.drop_column("shop_items", "is_available")
    if "category" in shop_columns:
        op.drop_column("shop_items", "category")
    if "slot" in shop_columns:
        op.drop_column("shop_items", "slot")

    indexes = _indexes("clan_wars")
    if "ix_war_defending_clan" in indexes:
        op.drop_index("ix_war_defending_clan", table_name="clan_wars")
    if "ix_war_attacking_clan" in indexes:
        op.drop_index("ix_war_attacking_clan", table_name="clan_wars")

    columns = _columns("clan_wars")
    if "updated_at" in columns:
        op.drop_column("clan_wars", "updated_at")
    if "ended_at" in columns:
        op.drop_column("clan_wars", "ended_at")
    if "winner_clan_id" in columns:
        op.drop_constraint("fk_clan_wars_winner_clan_id_clans", "clan_wars", type_="foreignkey")
        op.drop_column("clan_wars", "winner_clan_id")
