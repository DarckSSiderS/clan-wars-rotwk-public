"""Add clan levels, attack point spends, and war deployments.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""

from datetime import datetime, timedelta, timezone
import json

from alembic import op
import sqlalchemy as sa


revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def _backfill_legacy_attack_point_spends() -> None:
    bind = op.get_bind()
    rule_row = bind.execute(
        sa.text(
            "SELECT id, version, values FROM campaign_rule_sets "
            "ORDER BY CASE WHEN version = 1 THEN 0 ELSE 1 END, version LIMIT 1"
        )
    ).mappings().first()
    if rule_row is None:
        return

    values = rule_row["values"]
    if isinstance(values, str):
        values = json.loads(values)
    cooldown_hours = int(values.get("CLAN_ATTACK_COOLDOWN_HOURS", 96))
    now = datetime.now(timezone.utc)
    clans = bind.execute(
        sa.text(
            "SELECT id, next_attack_at FROM clans "
            "WHERE next_attack_at IS NOT NULL AND next_attack_at > :now"
        ),
        {"now": now},
    ).mappings()
    spends = sa.table(
        "clan_attack_point_spends",
        sa.column("clan_id", sa.Integer()),
        sa.column("war_id", sa.Integer()),
        sa.column("spent_by_user_id", sa.Integer()),
        sa.column("origin", sa.String()),
        sa.column("spent_at", sa.DateTime(timezone=True)),
        sa.column("recover_at", sa.DateTime(timezone=True)),
        sa.column("level_snapshot", sa.Integer()),
        sa.column("capacity_snapshot", sa.Integer()),
        sa.column("campaign_rule_set_id", sa.Integer()),
        sa.column("rule_version", sa.Integer()),
    )
    for clan in clans:
        recover_at = clan["next_attack_at"]
        bind.execute(
            spends.insert().values(
                clan_id=clan["id"],
                war_id=None,
                spent_by_user_id=None,
                origin="legacy_next_attack_at",
                spent_at=recover_at - timedelta(hours=cooldown_hours),
                recover_at=recover_at,
                level_snapshot=1,
                capacity_snapshot=1,
                campaign_rule_set_id=rule_row["id"],
                rule_version=rule_row["version"],
            )
        )


def upgrade():
    op.add_column(
        "clan_wars",
        sa.Column("campaign_rule_set_id", sa.Integer(), nullable=True),
    )
    op.add_column("clan_wars", sa.Column("rules_snapshot", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_clan_wars_campaign_rule_set",
        "clan_wars",
        "campaign_rule_sets",
        ["campaign_rule_set_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "clan_level_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clan_id", sa.Integer(), nullable=False),
        sa.Column("previous_level", sa.Integer(), nullable=False),
        sa.Column("new_level", sa.Integer(), nullable=False),
        sa.Column("active_member_count", sa.Integer(), nullable=False),
        sa.Column("territory_count", sa.Integer(), nullable=False),
        sa.Column("influence", sa.Integer(), nullable=False),
        sa.Column("campaign_rule_set_id", sa.Integer(), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["clan_id"], ["clans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["campaign_rule_set_id"],
            ["campaign_rule_sets.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_clan_level_events_clan_time",
        "clan_level_events",
        ["clan_id", "occurred_at"],
    )

    op.create_table(
        "clan_attack_point_spends",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clan_id", sa.Integer(), nullable=False),
        sa.Column("war_id", sa.Integer(), nullable=True),
        sa.Column("spent_by_user_id", sa.Integer(), nullable=True),
        sa.Column("origin", sa.String(length=40), nullable=False),
        sa.Column("spent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recover_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level_snapshot", sa.Integer(), nullable=False),
        sa.Column("capacity_snapshot", sa.Integer(), nullable=False),
        sa.Column("campaign_rule_set_id", sa.Integer(), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("refund_reason", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["clan_id"], ["clans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["war_id"], ["clan_wars.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["spent_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["refunded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["campaign_rule_set_id"],
            ["campaign_rule_sets.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "uq_attack_point_spend_war_clan",
        "clan_attack_point_spends",
        ["war_id", "clan_id"],
        unique=True,
        postgresql_where=sa.text("war_id IS NOT NULL"),
        sqlite_where=sa.text("war_id IS NOT NULL"),
    )
    op.create_index(
        "ix_attack_point_clan_recover",
        "clan_attack_point_spends",
        ["clan_id", "recover_at"],
    )

    op.create_table(
        "war_deployments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("war_id", sa.Integer(), nullable=False),
        sa.Column("clan_id", sa.Integer(), nullable=False),
        sa.Column("claim_sequence", sa.Integer(), nullable=False),
        sa.Column("source_territory_id", sa.Integer(), nullable=True),
        sa.Column("territory_count_snapshot", sa.Integer(), nullable=False),
        sa.Column("defense_rule", sa.String(length=64), nullable=False),
        sa.Column("initial_role", sa.String(length=16), nullable=False),
        sa.Column("current_role", sa.String(length=16), nullable=False),
        sa.Column("eligibility_scope", sa.String(length=20), nullable=False),
        sa.Column("assigned_by_user_id", sa.Integer(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("campaign_rule_set_id", sa.Integer(), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("attack_lock_released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("role_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["war_id"], ["clan_wars.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clan_id"], ["clans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_territory_id"],
            ["territories.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["campaign_rule_set_id"],
            ["campaign_rule_sets.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("war_id", "clan_id", name="uq_war_deployment_war_clan"),
        sa.UniqueConstraint(
            "war_id",
            "claim_sequence",
            name="uq_war_deployment_claim_sequence",
        ),
    )
    op.create_index(
        "ix_war_deployments_clan_role",
        "war_deployments",
        ["clan_id", "current_role"],
    )

    op.create_table(
        "war_deployment_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deployment_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("external_uuid_snapshot", sa.String(length=80), nullable=False),
        sa.Column("nickname_snapshot", sa.String(length=120), nullable=False),
        sa.Column("username_snapshot", sa.String(length=120), nullable=False),
        sa.Column("avatar_url_snapshot", sa.String(), nullable=True),
        sa.Column("membership_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["deployment_id"],
            ["war_deployments.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "deployment_id",
            "user_id",
            name="uq_war_deployment_member",
        ),
    )
    op.create_index(
        "uq_active_attack_deployment_member_user",
        "war_deployment_members",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
        sqlite_where=sa.text("released_at IS NULL"),
    )
    op.create_index(
        "ix_war_deployment_members_deployment",
        "war_deployment_members",
        ["deployment_id"],
    )

    op.add_column(
        "clan_war_match_results",
        sa.Column("winner_deployment_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "clan_war_match_results",
        sa.Column("loser_deployment_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "clan_war_match_results",
        sa.Column("winner_participation_share", sa.Float(), nullable=True),
    )
    op.add_column(
        "clan_war_match_results",
        sa.Column("loser_participation_share", sa.Float(), nullable=True),
    )
    op.add_column(
        "clan_war_match_results",
        sa.Column("winner_eligibility_code", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "clan_war_match_results",
        sa.Column("loser_eligibility_code", sa.String(length=80), nullable=True),
    )
    op.create_foreign_key(
        "fk_war_match_result_winner_deployment",
        "clan_war_match_results",
        "war_deployments",
        ["winner_deployment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_war_match_result_loser_deployment",
        "clan_war_match_results",
        "war_deployments",
        ["loser_deployment_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _backfill_legacy_attack_point_spends()


def downgrade():
    op.drop_constraint(
        "fk_war_match_result_loser_deployment",
        "clan_war_match_results",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_war_match_result_winner_deployment",
        "clan_war_match_results",
        type_="foreignkey",
    )
    op.drop_column("clan_war_match_results", "loser_eligibility_code")
    op.drop_column("clan_war_match_results", "winner_eligibility_code")
    op.drop_column("clan_war_match_results", "loser_participation_share")
    op.drop_column("clan_war_match_results", "winner_participation_share")
    op.drop_column("clan_war_match_results", "loser_deployment_id")
    op.drop_column("clan_war_match_results", "winner_deployment_id")

    op.drop_index(
        "ix_war_deployment_members_deployment",
        table_name="war_deployment_members",
    )
    op.drop_index(
        "uq_active_attack_deployment_member_user",
        table_name="war_deployment_members",
    )
    op.drop_table("war_deployment_members")
    op.drop_index("ix_war_deployments_clan_role", table_name="war_deployments")
    op.drop_table("war_deployments")
    op.drop_index("ix_attack_point_clan_recover", table_name="clan_attack_point_spends")
    op.drop_index("uq_attack_point_spend_war_clan", table_name="clan_attack_point_spends")
    op.drop_table("clan_attack_point_spends")
    op.drop_index("ix_clan_level_events_clan_time", table_name="clan_level_events")
    op.drop_table("clan_level_events")

    op.drop_constraint(
        "fk_clan_wars_campaign_rule_set",
        "clan_wars",
        type_="foreignkey",
    )
    op.drop_column("clan_wars", "rules_snapshot")
    op.drop_column("clan_wars", "campaign_rule_set_id")
