"""Restore each attack point after 60 hours, including pending old timers.

Revision ID: a3p4q5r6s7t8
Revises: z2o3p4q5r6s7
"""
from datetime import datetime, timedelta, timezone
import json

from alembic import op
import sqlalchemy as sa

from app.core.campaign_rules import default_campaign_rule_values


revision = "a3p4q5r6s7t8"
down_revision = "z2o3p4q5r6s7"
branch_labels = None
depends_on = None

RULE_KEY = "CLAN_ATTACK_COOLDOWN_HOURS"
RULE_REASON = "attack_points_60_hours_20260911"
BACKUP_TABLE = "attack_point_60h_migration_backup"
REDUCTION = timedelta(hours=36)


def _utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _values(raw):
    return json.loads(raw) if isinstance(raw, str) else dict(raw)


def _insert_rules(bind, values, reason):
    version = bind.execute(sa.text(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM campaign_rule_sets"
    )).scalar_one()
    bind.execute(sa.text("UPDATE campaign_rule_sets SET is_active = false WHERE is_active = true"))
    rules = sa.table("campaign_rule_sets", sa.column("version"), sa.column("values", sa.JSON()),
                     sa.column("is_active", sa.Boolean()), sa.column("reason"))
    bind.execute(rules.insert().values(version=version, values=values, is_active=True, reason=reason))


def _effective_now(bind):
    paused = bind.execute(sa.text(
        "SELECT paused_at FROM campaign_settings WHERE is_paused = true"
    )).scalar()
    return _utc(paused) if paused else datetime.now(timezone.utc)


def _sync_clans(bind, clan_ids, now):
    raw = bind.execute(sa.text('SELECT "values" FROM campaign_rule_sets WHERE is_active = true')).scalar_one()
    rules = _values(raw)
    clans = sa.table("clans", sa.column("id"), sa.column("next_attack_at", sa.DateTime(timezone=True)))
    for clan_id in clan_ids:
        level = bind.execute(sa.text("SELECT level FROM clans WHERE id = :id"), {"id": clan_id}).scalar()
        if level is None:
            continue
        capacity = int(rules[f"CLAN_LEVEL_{min(5, max(1, int(level or 1)))}_ATTACK_CAPACITY"])
        recoveries = sorted(_utc(value) for value in bind.execute(sa.text(
            "SELECT recover_at FROM clan_attack_point_spends WHERE clan_id = :id AND refunded_at IS NULL"
        ), {"id": clan_id}).scalars() if _utc(value) > now)
        next_at = recoveries[0] if recoveries and len(recoveries) >= capacity else None
        bind.execute(clans.update().where(clans.c.id == clan_id).values(next_attack_at=next_at))


def _migrate_pending(bind, now):
    backup = sa.Table(BACKUP_TABLE, sa.MetaData(), autoload_with=bind)
    spends = sa.table("clan_attack_point_spends", sa.column("id"), sa.column("recover_at", sa.DateTime(timezone=True)))
    rows = bind.execute(sa.text('''
        SELECT spend.id, spend.clan_id, spend.recover_at, rules."values"
        FROM clan_attack_point_spends spend
        JOIN campaign_rule_sets rules ON rules.id = spend.campaign_rule_set_id
        WHERE spend.refunded_at IS NULL
          AND NOT EXISTS (SELECT 1 FROM attack_point_60h_migration_backup saved WHERE saved.spend_id = spend.id)
    ''')).mappings().all()
    changed_clans = set()
    for row in rows:
        previous = _utc(row["recover_at"])
        if previous <= now or _values(row["values"]).get(RULE_KEY) != 96:
            continue
        # Subtract only the changed cooldown. Preserve any campaign-pause extension.
        updated = previous - REDUCTION
        bind.execute(backup.insert().values(spend_id=row["id"], clan_id=row["clan_id"],
                                            previous_recover_at=previous, updated_recover_at=updated))
        bind.execute(spends.update().where(spends.c.id == row["id"]).values(recover_at=updated))
        changed_clans.add(row["clan_id"])
    _sync_clans(bind, changed_clans, now)


def upgrade():
    bind = op.get_bind()
    op.create_table(
        BACKUP_TABLE,
        sa.Column("spend_id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("clan_id", sa.Integer(), nullable=False),
        sa.Column("previous_recover_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_recover_at", sa.DateTime(timezone=True), nullable=False),
    )
    current = bind.execute(sa.text('SELECT id, "values" FROM campaign_rule_sets WHERE is_active = true')).mappings().first()
    values = _values(current["values"]) if current else default_campaign_rule_values()
    if current is None or values.get(RULE_KEY) != 60:
        previous_id = current["id"] if current else 0
        _insert_rules(bind, {**values, RULE_KEY: 60}, f"{RULE_REASON}:previous_rule_set_id={previous_id}")
    _migrate_pending(bind, _effective_now(bind))


def downgrade():
    bind = op.get_bind()
    current = bind.execute(sa.text(
        "SELECT version, reason FROM campaign_rule_sets WHERE is_active = true"
    )).mappings().one()
    prefix = f"{RULE_REASON}:previous_rule_set_id="
    if current["reason"].startswith(prefix):
        previous = bind.execute(sa.text(
            'SELECT "values" FROM campaign_rule_sets WHERE id = :id'
        ), {"id": int(current["reason"][len(prefix):])}).scalar()
        if previous is not None:
            _insert_rules(bind, _values(previous), "attack_points_restore_previous_rules_20260911")
    saved = sa.Table(BACKUP_TABLE, sa.MetaData(), autoload_with=bind)
    spends = sa.table("clan_attack_point_spends", sa.column("id"), sa.column("refunded_at"),
                      sa.column("recover_at", sa.DateTime(timezone=True)))
    rows = bind.execute(saved.select()).mappings().all()
    for row in rows:
        # Do not overwrite subsequent refunds or manual deadline changes.
        bind.execute(spends.update().where(
            spends.c.id == row["spend_id"], spends.c.refunded_at.is_(None),
            spends.c.recover_at == row["updated_recover_at"],
        ).values(recover_at=row["previous_recover_at"]))
    _sync_clans(bind, {row["clan_id"] for row in rows}, _effective_now(bind))
    op.drop_table(BACKUP_TABLE)
