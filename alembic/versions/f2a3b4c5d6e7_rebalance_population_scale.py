"""Перевести население на компактный игровой масштаб.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
"""

from alembic import op
import sqlalchemy as sa

from app.core.campaign_rules import default_campaign_rule_values


revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


POPULATION_RULES = {
    "POPULATION_BASE_GROWTH_PERCENT": 4,
    "POPULATION_FLAT_GROWTH_PER_LEVEL": 20,
    "POPULATION_MAXIMUM": 4_000,
    "POPULATION_INCOME_BONUS_CAP_PERCENT": 20,
    "POPULATION_PER_INCOME_PERCENT": 100,
}
RULE_SET_REASON = "population_scale_middle_earth"


def _merge_population_rules(current_values: dict | None) -> dict:
    merged = default_campaign_rule_values()
    merged.update({
        key: value
        for key, value in (current_values or {}).items()
        if key in merged
    })
    merged.update(POPULATION_RULES)
    return merged


def _activate_population_rules(bind) -> None:
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
            values=_merge_population_rules(current_values),
            is_active=True,
            created_by_user_id=None,
            reason=RULE_SET_REASON,
        )
    )


def upgrade():
    bind = op.get_bind()
    _activate_population_rules(bind)
    bind.execute(
        sa.text(
            "UPDATE territories SET population = 4000 "
            "WHERE COALESCE(is_playable, true) = true AND population > 4000 "
            "AND lower(name) NOT IN ('тол-фалас', 'tol-falas', 'tol falas')"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE clan_assets SET description = :description "
            "WHERE key = 'ents_seed'"
        ),
        {
            "description": (
                "Прирост населения за уровень: базовые +4% и +20 жителей; "
                "реликвия добавляет I +1%, II +2%, III +3%."
            )
        },
    )


def downgrade():
    bind = op.get_bind()
    current_id = bind.execute(
        sa.text(
            "SELECT id FROM campaign_rule_sets WHERE reason = :reason "
            "ORDER BY version DESC LIMIT 1"
        ),
        {"reason": RULE_SET_REASON},
    ).scalar()
    if current_id is None:
        return
    bind.execute(
        sa.text("DELETE FROM campaign_rule_sets WHERE id = :id"),
        {"id": current_id},
    )
    previous_id = bind.execute(
        sa.text("SELECT id FROM campaign_rule_sets ORDER BY version DESC LIMIT 1")
    ).scalar()
    if previous_id is not None:
        bind.execute(
            sa.text("UPDATE campaign_rule_sets SET is_active = true WHERE id = :id"),
            {"id": previous_id},
        )
