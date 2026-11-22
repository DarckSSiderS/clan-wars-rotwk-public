"""Complete the economy balance contract from document section 55.

Revision ID: w9l0m1n2o3p4
Revises: v8k9l0m1n2o3
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa

from app.core.campaign_rules import default_campaign_rule_values
from app.core.territory_resource_balance import TERRITORY_BALANCE


revision = "w9l0m1n2o3p4"
down_revision = "v8k9l0m1n2o3"
branch_labels = None
depends_on = None


RULE_SET_REASON = "economy_v5_section_55"

RULE_OVERRIDES = {
    "POPULATION_BASE_GOLD_COST": 100,
    "POPULATION_GOLD_COST_PER_LEVEL": 25,
    "POPULATION_GOLD_COST_WEALTH_PERCENT": 100,
    "POPULATION_BASE_WOOD_COST": 1,
    "POPULATION_WOOD_COST_PER_LEVEL": 0,
    "FORTIFICATION_BASE_GOLD_COST": 100,
    "FORTIFICATION_GOLD_COST_PER_LEVEL": 30,
    "FORTIFICATION_BASE_IRON_COST": 1,
    "FORTIFICATION_IRON_COST_PER_LEVEL": 0,
    "FORTIFICATION_MITHRIL_START_LEVEL": 10,
    "OFFENSE_BASE_GOLD_COST": 100,
    "OFFENSE_GOLD_COST_PER_LEVEL": 30,
    "OFFENSE_BASE_IRON_COST": 1,
    "OFFENSE_IRON_COST_PER_LEVEL": 0,
    "OFFENSE_BASE_FOOD_COST": 0,
    "OFFENSE_FOOD_LEVEL_DIVISOR": 5,
    "OFFENSE_FOOD_COST_PER_STEP": 1,
    "PORT_BASE_GOLD_COST": 50,
    "PORT_GOLD_COST_PER_LEVEL": 15,
    "PORT_BASE_WOOD_COST": 0,
    "PORT_WOOD_COST_PER_LEVEL": 1,
    "PORT_WOOD_LEVEL_DIVISOR": 5,
    "PORT_BASE_IRON_COST": 0,
    "PORT_IRON_LEVEL_DIVISOR": 5,
    "PORT_IRON_COST_PER_STEP": 1,
    "FLEET_BASE_GOLD_COST": 50,
    "FLEET_GOLD_COST_PER_LEVEL": 15,
    "FLEET_BASE_WOOD_COST": 0,
    "FLEET_WOOD_COST_PER_LEVEL": 1,
    "FLEET_WOOD_LEVEL_DIVISOR": 5,
    "FLEET_BASE_IRON_COST": 0,
    "FLEET_IRON_COST_PER_LEVEL": 1,
    "FLEET_IRON_LEVEL_DIVISOR": 5,
    "FLEET_BASE_FOOD_COST": 0,
    "FLEET_FOOD_LEVEL_DIVISOR": 5,
    "FLEET_FOOD_COST_PER_STEP": 1,
}


RELIC_COSTS = {
    "royal_charter": (1900, 3, 3, 0, 0),
    "red_arrow": (1900, 2, 4, 1, 0),
    "iron_crown": (1900, 5, 0, 1, 0),
    "war_foundry": (2250, 5, 0, 3, 2),
    "merchant_guild": (2250, 0, 6, 3, 2),
    "white_tree": (2250, 0, 5, 2, 2),
    "dwarf_anvil": (2250, 6, 0, 1, 2),
    "ents_seed": (2250, 0, 7, 2, 1),
    "mordor_forge": (2250, 4, 0, 4, 2),
    "helms_horn": (2250, 5, 3, 0, 2),
    "mithril_standard": (2600, 4, 2, 2, 4),
    "granite_bastion": (2600, 6, 1, 0, 4),
    "palantir": (2600, 2, 2, 4, 3),
    "ring_of_barahir": (2600, 2, 1, 4, 4),
    "galadhrim_mirror": (2600, 0, 5, 3, 4),
}


PREVIOUS_RELIC_COSTS = {
    "royal_charter": (1109, 3, 3, 0, 0),
    "red_arrow": (1109, 2, 4, 1, 0),
    "iron_crown": (1109, 4, 0, 1, 0),
    "war_foundry": (1478, 5, 0, 3, 2),
    "merchant_guild": (1478, 0, 6, 3, 2),
    "white_tree": (1478, 0, 5, 2, 2),
    "dwarf_anvil": (1478, 6, 0, 1, 2),
    "ents_seed": (1478, 0, 7, 2, 1),
    "mordor_forge": (1478, 4, 0, 4, 2),
    "helms_horn": (1478, 5, 3, 0, 2),
    "mithril_standard": (1848, 4, 2, 2, 4),
    "granite_bastion": (1848, 6, 1, 0, 4),
    "palantir": (1848, 2, 2, 4, 3),
    "ring_of_barahir": (1848, 2, 1, 4, 4),
    "galadhrim_mirror": (1848, 0, 5, 3, 4),
}


RESOURCE_COST_COLUMNS = (
    "gold_cost",
    "iron_cost",
    "wood_cost",
    "food_cost",
    "mithril_cost",
)


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


def _apply_territory_balance(bind) -> None:
    statement = sa.text(
        "UPDATE territories SET resource_type=:resource_type, "
        "resource_output=:resource_output, "
        "secondary_resource_type=:secondary_resource_type, "
        "resource_wealth=:resource_wealth, "
        "influence_value=:influence_value, "
        "required_influence=:required_influence, "
        "required_territories=:required_territories, "
        "stronghold_power=:stronghold_power WHERE name=:name"
    )
    for name, balance in TERRITORY_BALANCE.items():
        bind.execute(
            statement,
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


def _previous_territory_values(balance) -> tuple[int, int, int, int, int]:
    if balance.stronghold_power == 0:
        return {
            40: (30, 20, 30, 0, 0),
            45: (45, 30, 60, 0, 0),
            55: (60, 40, 90, 0, 0),
            60: (75, 50, 120, 0, 0),
        }[balance.resource_wealth]
    return {
        140: (120, 90, 300, 5, 3),
        150: (160, 120, 400, 6, 4),
        160: (220, 160, 500, 8, 5),
    }[balance.resource_wealth]


def _restore_previous_territory_balance(bind) -> None:
    statement = sa.text(
        "UPDATE territories SET resource_wealth=:resource_wealth, "
        "influence_value=:influence_value, "
        "required_influence=:required_influence, "
        "required_territories=:required_territories, "
        "stronghold_power=:stronghold_power "
        "WHERE name=:name AND resource_wealth=:current_resource_wealth "
        "AND influence_value=:current_influence_value "
        "AND required_influence=:current_required_influence "
        "AND required_territories=:current_required_territories "
        "AND stronghold_power=:current_stronghold_power"
    )
    for name, balance in TERRITORY_BALANCE.items():
        previous = _previous_territory_values(balance)
        bind.execute(
            statement,
            {
                "name": name,
                "resource_wealth": previous[0],
                "influence_value": previous[1],
                "required_influence": previous[2],
                "required_territories": previous[3],
                "stronghold_power": previous[4],
                "current_resource_wealth": balance.resource_wealth,
                "current_influence_value": balance.influence_value,
                "current_required_influence": balance.required_influence,
                "current_required_territories": balance.required_territories,
                "current_stronghold_power": balance.stronghold_power,
            },
        )


def _apply_relic_costs(bind, costs: dict[str, tuple[int, ...]]) -> None:
    assignments = ", ".join(f"{column}=:{column}" for column in RESOURCE_COST_COLUMNS)
    statement = sa.text(
        f"UPDATE clan_assets SET {assignments} WHERE key=:key"  # noqa: S608
    )
    for key, values in costs.items():
        bind.execute(
            statement,
            {"key": key, **dict(zip(RESOURCE_COST_COLUMNS, values, strict=True))},
        )


def _restore_previous_relic_costs(bind) -> None:
    assignments = ", ".join(
        f"{column}=:previous_{column}" for column in RESOURCE_COST_COLUMNS
    )
    guards = " AND ".join(
        f"{column}=:current_{column}" for column in RESOURCE_COST_COLUMNS
    )
    statement = sa.text(
        f"UPDATE clan_assets SET {assignments} WHERE key=:key AND {guards}"  # noqa: S608
    )
    for key, previous in PREVIOUS_RELIC_COSTS.items():
        current = RELIC_COSTS[key]
        params = {"key": key}
        params.update(
            {
                f"previous_{column}": value
                for column, value in zip(RESOURCE_COST_COLUMNS, previous, strict=True)
            }
        )
        params.update(
            {
                f"current_{column}": value
                for column, value in zip(RESOURCE_COST_COLUMNS, current, strict=True)
            }
        )
        bind.execute(statement, params)


def _restore_previous_rules(bind) -> None:
    current_id = bind.execute(
        sa.text(
            "SELECT id FROM campaign_rule_sets WHERE reason=:reason "
            "ORDER BY version DESC LIMIT 1"
        ),
        {"reason": RULE_SET_REASON},
    ).scalar()
    if current_id is None:
        return
    bind.execute(
        sa.text("DELETE FROM campaign_rule_sets WHERE id=:id"),
        {"id": current_id},
    )
    previous_id = bind.execute(
        sa.text("SELECT id FROM campaign_rule_sets ORDER BY version DESC LIMIT 1")
    ).scalar()
    if previous_id is not None:
        bind.execute(
            sa.text("UPDATE campaign_rule_sets SET is_active=true WHERE id=:id"),
            {"id": previous_id},
        )


def upgrade() -> None:
    bind = op.get_bind()
    _activate_rules(bind)
    _apply_territory_balance(bind)
    _apply_relic_costs(bind, RELIC_COSTS)


def downgrade() -> None:
    bind = op.get_bind()
    _restore_previous_relic_costs(bind)
    _restore_previous_territory_balance(bind)
    _restore_previous_rules(bind)
