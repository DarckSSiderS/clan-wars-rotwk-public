"""Включить суточную экономику v2.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
"""

from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa

from app.core.campaign_rules import default_campaign_rule_values
from app.core.economy_balance import GREAT_CITY_BALANCE


revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


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

ECONOMY_RULE_PREFIXES = (
    "ECONOMY_",
    "POPULATION_",
    "FORTIFICATION_",
    "OFFENSE_",
    "PORT_",
    "FLEET_",
    "RELIC_",
    "CARAVAN_",
    "TERRITORY_RESOURCE_",
    "TERRITORY_MIN_RESOURCE_",
    "TERRITORY_MAX_UPGRADE_",
)
ECONOMY_RULE_KEYS = frozenset({
    "CLAN_LEVEL_2_INFLUENCE",
    "CLAN_LEVEL_3_INFLUENCE",
    "CLAN_LEVEL_4_INFLUENCE",
    "CLAN_LEVEL_5_INFLUENCE",
})


def _merge_economy_v2_rules(current_values: dict | None) -> dict:
    defaults = default_campaign_rule_values()
    merged = dict(defaults)
    for key, value in (current_values or {}).items():
        is_economy_rule = key in ECONOMY_RULE_KEYS or key.startswith(
            ECONOMY_RULE_PREFIXES
        )
        if key in defaults and not is_economy_rule:
            merged[key] = value
    return merged


def _activate_rules_v2(bind) -> None:
    current_values = bind.execute(
        sa.text(
            'SELECT "values" FROM campaign_rule_sets '
            "WHERE is_active = true ORDER BY version DESC LIMIT 1"
        )
    ).scalar()
    version = bind.execute(
        sa.text("SELECT COALESCE(MAX(version), 0) + 1 FROM campaign_rule_sets")
    ).scalar_one()
    bind.execute(sa.text("UPDATE campaign_rule_sets SET is_active = false"))
    rule_sets = sa.table(
        "campaign_rule_sets",
        sa.column("version", sa.Integer()),
        sa.column("values", sa.JSON()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_by_user_id", sa.Integer()),
        sa.column("reason", sa.String()),
    )
    bind.execute(
        rule_sets.insert().values(
            version=version,
            values=_merge_economy_v2_rules(current_values),
            is_active=True,
            created_by_user_id=None,
            reason="economy_v2_daily_balance",
        )
    )


def _normalize_territories(bind) -> None:
    now = datetime.now(timezone.utc)
    bind.execute(
        sa.text(
            "UPDATE territories SET resource_income_ready_at = :ready_at, "
            "last_resource_payout_at = NULL "
            "WHERE owner_clan_id IS NOT NULL "
            "AND lower(name) NOT IN ('тол-фалас', 'tol-falas', 'tol falas')"
        ),
        {"ready_at": now + timedelta(hours=72)},
    )

    ordinary = bind.execute(
        sa.text(
            "SELECT id FROM territories WHERE COALESCE(stronghold_power, 0) = 0 "
            "AND lower(name) NOT IN ('тол-фалас', 'tol-falas', 'tol falas') "
            "ORDER BY COALESCE(required_influence, 0) DESC, "
            "COALESCE(resource_wealth, 0) DESC, id"
        )
    ).scalars().all()
    for index, territory_id in enumerate(ordinary):
        if index < 12:
            income, influence, required = 70, 50, 120
        elif index < 35:
            income, influence, required = 55, 35, 60
        else:
            income, influence, required = 40, 25, 30
        bind.execute(
            sa.text(
                "UPDATE territories SET resource_wealth=:income, "
                "influence_value=:influence, required_influence=:required, "
                "resource_output=1 WHERE id=:territory_id"
            ),
            {
                "income": income,
                "influence": influence,
                "required": required,
                "territory_id": territory_id,
            },
        )

    rows = bind.execute(sa.text("SELECT id, name, resource_type FROM territories")).mappings()
    for row in rows:
        balance = GREAT_CITY_BALANCE.get((row["name"] or "").strip().casefold())
        if not balance:
            continue
        income, influence, required, territories_required, power = balance
        primary = row["resource_type"] or "iron"
        secondary = next(
            resource for resource in ("wood", "iron", "food", "mithril")
            if resource != primary
        )
        bind.execute(
            sa.text(
                "UPDATE territories SET resource_wealth=:income, "
                "influence_value=:influence, required_influence=:required, "
                "required_territories=:territories_required, stronghold_power=:power, "
                "resource_output=1, secondary_resource_type=:secondary WHERE id=:id"
            ),
            {
                "income": income,
                "influence": influence,
                "required": required,
                "territories_required": territories_required,
                "power": power,
                "secondary": secondary,
                "id": row["id"],
            },
        )


def _normalize_relics(bind) -> None:
    for key, costs in RELIC_BALANCE.items():
        gold, iron, wood, food, mithril = costs
        bind.execute(
            sa.text(
                "UPDATE clan_assets SET gold_cost=:gold, iron_cost=:iron, "
                "wood_cost=:wood, food_cost=:food, mithril_cost=:mithril, "
                "required_influence_level_1=175, required_influence_level_2=525, "
                "required_influence_level_3=1050, upgrade_multiplier=5 "
                "WHERE key=:key"
            ),
            {
                "key": key,
                "gold": gold,
                "iron": iron,
                "wood": wood,
                "food": food,
                "mithril": mithril,
            },
        )


def upgrade():
    op.add_column(
        "territories",
        sa.Column("resource_income_ready_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "territories",
        sa.Column("last_resource_payout_at", sa.DateTime(timezone=True), nullable=True),
    )
    bind = op.get_bind()
    _activate_rules_v2(bind)
    _normalize_territories(bind)
    _normalize_relics(bind)


def downgrade():
    bind = op.get_bind()
    current = bind.execute(
        sa.text(
            "SELECT id FROM campaign_rule_sets WHERE reason='economy_v2_daily_balance' "
            "ORDER BY version DESC LIMIT 1"
        )
    ).scalar()
    if current is not None:
        bind.execute(sa.text("DELETE FROM campaign_rule_sets WHERE id=:id"), {"id": current})
        previous = bind.execute(
            sa.text("SELECT id FROM campaign_rule_sets ORDER BY version DESC LIMIT 1")
        ).scalar()
        if previous is not None:
            bind.execute(
                sa.text("UPDATE campaign_rule_sets SET is_active=true WHERE id=:id"),
                {"id": previous},
            )
    op.drop_column("territories", "last_resource_payout_at")
    op.drop_column("territories", "resource_income_ready_at")
