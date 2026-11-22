"""Добавляет Воевод клана и снимок командира похода.

Revision ID: j6e7f8a9b0c1
Revises: i5d6e7f8a9b0
Create Date: 2026-08-22 18:00:00.000000
"""

from alembic import op
import json
import sqlalchemy as sa


revision = "j6e7f8a9b0c1"
down_revision = "i5d6e7f8a9b0"
branch_labels = None
depends_on = None


RULE_OVERRIDES = {
    "TERRITORY_RESOURCE_READY_HOURS": 48,
    "CLAN_LEVEL_2_ACTIVE_MEMBERS": 11,
    "CLAN_LEVEL_2_TERRITORIES": 2,
    "CLAN_LEVEL_2_INFLUENCE": 140,
    "CLAN_LEVEL_3_ACTIVE_MEMBERS": 17,
    "CLAN_LEVEL_3_TERRITORIES": 4,
    "CLAN_LEVEL_3_INFLUENCE": 230,
    "CLAN_LEVEL_4_ACTIVE_MEMBERS": 22,
    "CLAN_LEVEL_4_TERRITORIES": 6,
    "CLAN_LEVEL_4_INFLUENCE": 340,
    "CLAN_LEVEL_5_ACTIVE_MEMBERS": 30,
    "CLAN_LEVEL_5_TERRITORIES": 10,
    "CLAN_LEVEL_5_INFLUENCE": 500,
}


def _activate_updated_rules(bind) -> None:
    active = bind.execute(
        sa.text(
            'SELECT "values" FROM campaign_rule_sets '
            "WHERE is_active = true ORDER BY version DESC LIMIT 1"
        )
    ).scalar()
    if active is None:
        return
    if isinstance(active, str):
        active = json.loads(active)
    values = dict(active)
    values.update(RULE_OVERRIDES)
    version = bind.execute(
        sa.text("SELECT COALESCE(MAX(version), 0) + 1 FROM campaign_rule_sets")
    ).scalar_one()
    bind.execute(sa.text("UPDATE campaign_rule_sets SET is_active = false"))
    table = sa.table(
        "campaign_rule_sets",
        sa.column("version", sa.Integer()),
        sa.column("values", sa.JSON()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_by_user_id", sa.Integer()),
        sa.column("reason", sa.String()),
    )
    bind.execute(
        table.insert().values(
            version=version,
            values=values,
            is_active=True,
            created_by_user_id=None,
            reason="warlords_and_clan_level_rules",
        )
    )


def _shorten_pending_resource_preparation(bind) -> None:
    if bind.dialect.name == "sqlite":
        ready_at = "datetime(owned_since, '+48 hours')"
    else:
        ready_at = "owned_since + INTERVAL '48 hours'"
    bind.execute(
        sa.text(
            "UPDATE territories "
            f"SET resource_income_ready_at = {ready_at} "
            "WHERE owner_clan_id IS NOT NULL "
            "AND owned_since IS NOT NULL "
            f"AND (resource_income_ready_at IS NULL OR resource_income_ready_at > {ready_at})"
        )
    )


def _column_names(bind, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _index_names(bind, table_name: str) -> set[str]:
    return {
        index["name"]
        for index in sa.inspect(bind).get_indexes(table_name)
        if index.get("name")
    }


def _foreign_key_names(bind, table_name: str) -> set[str]:
    return {
        foreign_key["name"]
        for foreign_key in sa.inspect(bind).get_foreign_keys(table_name)
        if foreign_key.get("name")
    }


def _remove_stale_sqlite_batch_table(bind, table_name: str) -> None:
    if bind.dialect.name != "sqlite":
        return
    temporary_name = f"_alembic_tmp_{table_name}"
    inspector = sa.inspect(bind)
    if inspector.has_table(table_name) and inspector.has_table(temporary_name):
        op.drop_table(temporary_name)


def upgrade():
    bind = op.get_bind()
    _remove_stale_sqlite_batch_table(bind, "war_deployments")
    clan_member_columns = _column_names(bind, "clan_members")
    if "is_warlord" not in clan_member_columns:
        op.add_column(
            "clan_members",
            sa.Column(
                "is_warlord",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if "ix_clan_members_clan_warlord" not in _index_names(bind, "clan_members"):
        op.create_index(
            "ix_clan_members_clan_warlord",
            "clan_members",
            ["clan_id", "is_warlord"],
            unique=False,
        )

    deployment_columns = _column_names(bind, "war_deployments")
    deployment_foreign_keys = _foreign_key_names(bind, "war_deployments")
    with op.batch_alter_table("war_deployments") as batch_op:
        if "warlord_user_id" not in deployment_columns:
            batch_op.add_column(
                sa.Column("warlord_user_id", sa.Integer(), nullable=True)
            )
        if "warlord_username_snapshot" not in deployment_columns:
            batch_op.add_column(
                sa.Column(
                    "warlord_username_snapshot",
                    sa.String(length=120),
                    nullable=True,
                )
            )
        if "fk_war_deployments_warlord_user" not in deployment_foreign_keys:
            batch_op.create_foreign_key(
                "fk_war_deployments_warlord_user",
                "users",
                ["warlord_user_id"],
                ["id"],
                ondelete="SET NULL",
            )
    if (
        "ix_war_deployments_warlord_user"
        not in _index_names(bind, "war_deployments")
    ):
        op.create_index(
            "ix_war_deployments_warlord_user",
            "war_deployments",
            ["warlord_user_id"],
            unique=False,
        )

    _activate_updated_rules(bind)
    _shorten_pending_resource_preparation(bind)


def downgrade():
    bind = op.get_bind()
    if "ix_war_deployments_warlord_user" in _index_names(bind, "war_deployments"):
        op.drop_index("ix_war_deployments_warlord_user", table_name="war_deployments")
    deployment_columns = _column_names(bind, "war_deployments")
    with op.batch_alter_table("war_deployments") as batch_op:
        if "fk_war_deployments_warlord_user" in _foreign_key_names(
            bind, "war_deployments"
        ):
            batch_op.drop_constraint(
                "fk_war_deployments_warlord_user",
                type_="foreignkey",
            )
        if "warlord_username_snapshot" in deployment_columns:
            batch_op.drop_column("warlord_username_snapshot")
        if "warlord_user_id" in deployment_columns:
            batch_op.drop_column("warlord_user_id")
    if "ix_clan_members_clan_warlord" in _index_names(bind, "clan_members"):
        op.drop_index("ix_clan_members_clan_warlord", table_name="clan_members")
    if "is_warlord" in _column_names(bind, "clan_members"):
        with op.batch_alter_table("clan_members") as batch_op:
            batch_op.drop_column("is_warlord")
