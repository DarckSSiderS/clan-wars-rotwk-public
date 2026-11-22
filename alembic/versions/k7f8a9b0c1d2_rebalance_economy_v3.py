"""Перенастраивает темп экономики кампании.

Revision ID: k7f8a9b0c1d2
Revises: j6e7f8a9b0c1
Create Date: 2026-08-24 12:00:00.000000
"""

from alembic import op
import json
import sqlalchemy as sa


revision = "k7f8a9b0c1d2"
down_revision = "j6e7f8a9b0c1"
branch_labels = None
depends_on = None


RULE_SET_REASON = "economy_v3_population_naval_market_relics"
DISCOUNT_MULTIPLIER = 0.88

RULE_OVERRIDES = {
    "POPULATION_BASE_GOLD_COST": 150,
    "POPULATION_GOLD_COST_PER_LEVEL": 35,
    "POPULATION_GOLD_COST_WEALTH_PERCENT": 100,
    "POPULATION_BASE_WOOD_COST": 2,
    "POPULATION_WOOD_COST_PER_LEVEL": 1,
    "POPULATION_WOOD_LEVEL_DIVISOR": 2,
    "POPULATION_DEVELOPMENT_BONUS_FIRST_LEVELS_PERCENT": 12,
    "POPULATION_DEVELOPMENT_BONUS_LATER_LEVELS_PERCENT": 6,
    "POPULATION_DEVELOPMENT_BONUS_BREAK_LEVEL": 5,
    "PORT_BASE_GOLD_COST": 320,
    "PORT_GOLD_COST_PER_LEVEL": 80,
    "PORT_BASE_WOOD_COST": 3,
    "PORT_WOOD_LEVEL_DIVISOR": 2,
    "PORT_IRON_LEVEL_DIVISOR": 3,
    "FLEET_BASE_GOLD_COST": 380,
    "FLEET_GOLD_COST_PER_LEVEL": 95,
    "FLEET_BASE_WOOD_COST": 4,
    "FLEET_WOOD_LEVEL_DIVISOR": 2,
    "FLEET_IRON_LEVEL_DIVISOR": 2,
    "FLEET_BASE_FOOD_COST": 1,
    "FLEET_FOOD_LEVEL_DIVISOR": 3,
    "CARAVAN_GOLD_FEE_MULTIPLIER_PERCENT": 120,
}

RELIC_BALANCE = {
    "royal_charter": (1260, 3, 3, 0, 0),
    "red_arrow": (1260, 2, 4, 1, 0),
    "iron_crown": (1260, 5, 0, 1, 0),
    "war_foundry": (1680, 6, 0, 3, 2),
    "merchant_guild": (1680, 0, 7, 3, 2),
    "white_tree": (1680, 0, 6, 2, 2),
    "dwarf_anvil": (1680, 7, 0, 1, 2),
    "ents_seed": (1680, 0, 8, 2, 1),
    "mordor_forge": (1680, 5, 0, 4, 2),
    "helms_horn": (1680, 6, 3, 0, 2),
    "mithril_standard": (2100, 4, 2, 2, 4),
    "granite_bastion": (2100, 7, 1, 0, 4),
    "palantir": (2100, 2, 2, 4, 3),
    "ring_of_barahir": (2100, 2, 1, 4, 4),
    "galadhrim_mirror": (2100, 0, 6, 3, 4),
}


def _discounted_cost(amount: int) -> int:
    if amount <= 0:
        return 0
    return max(1, round(amount * DISCOUNT_MULTIPLIER))


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
            reason=RULE_SET_REASON,
        )
    )


def _update_relic_costs(bind, *, reverse: bool = False) -> None:
    for key, original_costs in RELIC_BALANCE.items():
        discounted_costs = tuple(_discounted_cost(value) for value in original_costs)
        expected, replacement = (
            (discounted_costs, original_costs) if reverse else (original_costs, discounted_costs)
        )
        params = {"key": key}
        assignments = []
        for column, old_value, new_value in zip(
            ("gold_cost", "iron_cost", "wood_cost", "food_cost", "mithril_cost"),
            expected,
            replacement,
        ):
            params[f"old_{column}"] = old_value
            params[f"new_{column}"] = new_value
            assignments.append(
                f"{column} = CASE WHEN {column} = :old_{column} "
                f"THEN :new_{column} ELSE {column} END"
            )
        bind.execute(
            sa.text(
                "UPDATE clan_assets SET " + ", ".join(assignments) + " WHERE key = :key"
            ),
            params,
        )


def upgrade():
    bind = op.get_bind()
    _activate_updated_rules(bind)
    _update_relic_costs(bind)


def downgrade():
    bind = op.get_bind()
    _update_relic_costs(bind, reverse=True)
    current = bind.execute(
        sa.text(
            "SELECT id FROM campaign_rule_sets WHERE reason = :reason "
            "ORDER BY version DESC LIMIT 1"
        ),
        {"reason": RULE_SET_REASON},
    ).scalar()
    if current is None:
        return
    bind.execute(sa.text("DELETE FROM campaign_rule_sets WHERE id = :id"), {"id": current})
    previous = bind.execute(
        sa.text("SELECT id FROM campaign_rule_sets ORDER BY version DESC LIMIT 1")
    ).scalar()
    if previous is not None:
        bind.execute(
            sa.text("UPDATE campaign_rule_sets SET is_active = true WHERE id = :id"),
            {"id": previous},
        )
