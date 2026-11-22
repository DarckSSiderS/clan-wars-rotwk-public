"""Set 60-hour wars and seed untouched neutral military development.

Revision ID: y1n2o3p4q5r6
Revises: x0m1n2o3p4q5
"""

import json

from alembic import op
import sqlalchemy as sa

from app.core.campaign_rules import default_campaign_rule_values
from app.core.territory_development import initial_military_level


revision = "y1n2o3p4q5r6"
down_revision = "x0m1n2o3p4q5"
branch_labels = None
depends_on = None

RULE_SET_REASON = "requirements_79_60_hour_wars"


def _insert_active_version(bind, values, reason):
    version = bind.execute(sa.text(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM campaign_rule_sets"
    )).scalar_one()
    bind.execute(sa.text("UPDATE campaign_rule_sets SET is_active = false"))
    table = sa.table(
        "campaign_rule_sets",
        sa.column("version", sa.Integer()),
        sa.column("values", sa.JSON()),
        sa.column("is_active", sa.Boolean()),
        sa.column("reason", sa.String()),
    )
    bind.execute(table.insert().values(
        version=version, values=values, is_active=True, reason=reason,
    ))


def _activate_rules(bind):
    raw = bind.execute(sa.text(
        'SELECT "values" FROM campaign_rule_sets WHERE is_active = true'
    )).scalar()
    values = json.loads(raw) if isinstance(raw, str) else raw
    if values and values.get("WAR_DURATION_HOURS") == 60:
        return
    merged = default_campaign_rule_values()
    merged.update(values or {})
    merged["WAR_DURATION_HOURS"] = 60
    _insert_active_version(bind, merged, RULE_SET_REASON)
    # Existing wars, attack-point recovery times and season snapshots retain
    # the terms under which they started.


def _seed_neutral_development(bind):
    rows = bind.execute(sa.text("""
        SELECT id, name, stronghold_power, has_port
        FROM territories
        WHERE owner_clan_id IS NULL AND is_playable = true
          AND status = 'neutral'
          AND COALESCE(offense_level, 0) = 0
          AND COALESCE(fortifications, 0) = 0
          AND COALESCE(development_level, 0) = 0
          AND COALESCE(port_level, 0) = 0
          AND COALESCE(fleet_level, 0) = 0
          AND NOT EXISTS (
              SELECT 1 FROM territory_ownership_history history
              WHERE history.territory_id = territories.id
          )
          AND NOT EXISTS (
              SELECT 1 FROM clan_wars war
              WHERE war.territory_id = territories.id AND war.status = 'active'
          )
    """)).mappings().all()
    for row in rows:
        level = initial_military_level(
            row["name"], stronghold_power=row["stronghold_power"] or 0,
        )
        if not level:
            continue
        bind.execute(sa.text("""
            UPDATE territories
            SET offense_level = :level, fortifications = :level,
                strategic_value = :strategic_value
            WHERE id = :id
        """), {
            "id": row["id"], "level": level,
            "strategic_value": round(level * 2 / (4 if row["has_port"] else 3), 1),
        })


def upgrade():
    bind = op.get_bind()
    _activate_rules(bind)
    _seed_neutral_development(bind)


def downgrade():
    bind = op.get_bind()
    current = bind.execute(sa.text(
        "SELECT id, version, reason FROM campaign_rule_sets WHERE is_active = true"
    )).mappings().first()
    if current and current["reason"] == RULE_SET_REASON:
        previous_values = bind.execute(sa.text(
            'SELECT "values" FROM campaign_rule_sets WHERE version < :version '
            "ORDER BY version DESC LIMIT 1"
        ), {"version": current["version"]}).scalar()
        if previous_values is not None:
            values = json.loads(previous_values) if isinstance(previous_values, str) else previous_values
            # Restoration is another version so future admin edits can still
            # use active.version + 1 without colliding with retained history.
            _insert_active_version(bind, values, "requirements_79_restore_previous_rules")
    # Keep referenced rule versions and earned territory development intact.
