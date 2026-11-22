"""Activate the fast lore economy and normalize territory specializations.

Revision ID: u7j8k9l0m1n2
Revises: t6i7j8k9l0m1
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa

from app.core.campaign_rules import default_campaign_rule_values
from app.core.territory_resource_balance import TERRITORY_BALANCE


revision = "u7j8k9l0m1n2"
down_revision = "t6i7j8k9l0m1"
branch_labels = None
depends_on = None


RULE_SET_REASON = "economy_v4_fast_lore_season"

RULE_OVERRIDES = {
    "CAMPAIGN_STARTING_GOLD": 100,
    "CAMPAIGN_STARTING_IRON": 6,
    "CAMPAIGN_STARTING_WOOD": 6,
    "CAMPAIGN_STARTING_FOOD": 3,
    "CAMPAIGN_STARTING_MITHRIL": 0,
    "POPULATION_BASE_GOLD_COST": 140,
    "POPULATION_GOLD_COST_PER_LEVEL": 60,
    "POPULATION_DEVELOPMENT_BONUS_FIRST_LEVELS_PERCENT": 8,
    "POPULATION_DEVELOPMENT_BONUS_LATER_LEVELS_PERCENT": 4,
    "FORTIFICATION_BASE_GOLD_COST": 280,
    "FORTIFICATION_GOLD_COST_PER_LEVEL": 140,
    "FORTIFICATION_BASE_IRON_COST": 2,
    "OFFENSE_BASE_GOLD_COST": 300,
    "OFFENSE_GOLD_COST_PER_LEVEL": 150,
    "OFFENSE_BASE_IRON_COST": 2,
    "PORT_BASE_GOLD_COST": 260,
    "PORT_GOLD_COST_PER_LEVEL": 110,
    "PORT_BASE_IRON_COST": 1,
    "FLEET_BASE_GOLD_COST": 320,
    "FLEET_GOLD_COST_PER_LEVEL": 130,
    "FLEET_BASE_WOOD_COST": 3,
    "CARAVAN_GOLD_FEE_MULTIPLIER_PERCENT": 100,
}


def _active_values(bind) -> dict:
    values = bind.execute(
        sa.text(
            'SELECT "values" FROM campaign_rule_sets '
            "WHERE is_active = true ORDER BY version DESC LIMIT 1"
        )
    ).scalar()
    if isinstance(values, str):
        values = json.loads(values)
    merged = default_campaign_rule_values()
    merged.update(values or {})
    merged.update(RULE_OVERRIDES)
    return merged


def _activate_rules(bind) -> None:
    values = _active_values(bind)
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
            reason=RULE_SET_REASON,
        )
    )


def _normalize_territories(bind) -> None:
    for name, balance in TERRITORY_BALANCE.items():
        bind.execute(
            sa.text(
                "UPDATE territories SET resource_type=:resource_type, "
                "resource_output=:resource_output, "
                "secondary_resource_type=:secondary_resource_type, "
                "resource_wealth=:resource_wealth, "
                "influence_value=:influence_value, "
                "required_influence=:required_influence, "
                "required_territories=:required_territories, "
                "stronghold_power=:stronghold_power WHERE name=:name"
            ),
            {
                "name": name,
                "resource_type": balance.resource_type,
                "resource_output": balance.resource_output,
                "secondary_resource_type": balance.secondary_resource_type,
                "resource_wealth": balance.resource_wealth,
                "influence_value": balance.influence_value,
                "required_influence": balance.required_influence,
                "required_territories": balance.required_territories,
                "stronghold_power": balance.stronghold_power,
            },
        )


def _migrate_untouched_clan_treasuries(bind) -> None:
    # Production had no active season, owned playable land, or ledger entries
    # when this preset was approved. The guards keep an already-used treasury
    # intact on other installations.
    bind.execute(
        sa.text(
            """
            UPDATE clans
            SET gold = :gold,
                iron = :iron,
                wood = :wood,
                food = :food,
                mithril = :mithril
            WHERE COALESCE(is_admin_clan, false) = false
              AND COALESCE(gold, 0) = 500
              AND COALESCE(iron, 0) = 10
              AND COALESCE(wood, 0) = 10
              AND COALESCE(food, 0) = 5
              AND COALESCE(mithril, 0) = 2
              AND NOT EXISTS (
                  SELECT 1 FROM resource_ledger ledger
                  WHERE ledger.clan_id = clans.id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM territories territory
                  WHERE territory.owner_clan_id = clans.id
                    AND lower(territory.name) NOT IN (
                        'тол-фалас', 'tol-falas', 'tol falas'
                    )
              )
            """
        ),
        {
            "gold": RULE_OVERRIDES["CAMPAIGN_STARTING_GOLD"],
            "iron": RULE_OVERRIDES["CAMPAIGN_STARTING_IRON"],
            "wood": RULE_OVERRIDES["CAMPAIGN_STARTING_WOOD"],
            "food": RULE_OVERRIDES["CAMPAIGN_STARTING_FOOD"],
            "mithril": RULE_OVERRIDES["CAMPAIGN_STARTING_MITHRIL"],
        },
    )


def upgrade() -> None:
    bind = op.get_bind()
    _activate_rules(bind)
    _normalize_territories(bind)
    _migrate_untouched_clan_treasuries(bind)


def downgrade() -> None:
    bind = op.get_bind()
    current = bind.execute(
        sa.text(
            "SELECT id, is_active FROM campaign_rule_sets WHERE reason=:reason "
            "ORDER BY version DESC LIMIT 1"
        ),
        {"reason": RULE_SET_REASON},
    ).mappings().first()
    if current is None:
        return
    was_active = bool(current["is_active"])
    bind.execute(
        sa.text("DELETE FROM campaign_rule_sets WHERE id=:id"),
        {"id": current["id"]},
    )
    if was_active:
        previous = bind.execute(
            sa.text("SELECT id FROM campaign_rule_sets ORDER BY version DESC LIMIT 1")
        ).scalar()
        if previous is not None:
            bind.execute(
                sa.text("UPDATE campaign_rule_sets SET is_active=true WHERE id=:id"),
                {"id": previous},
            )
    # Territory and guarded treasury normalization is intentionally retained:
    # a downgrade must not restore the broken all-wood fallback or overwrite
    # resources earned after deployment.
