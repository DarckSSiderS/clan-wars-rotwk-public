"""Add immutable versioned campaign rule sets.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""

from alembic import op
import sqlalchemy as sa


revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


INITIAL_CAMPAIGN_RULE_VALUES = {
    "ATTACK_INFLUENCE_FORTIFICATION_MULTIPLIER": 6,
    "ATTACK_INFLUENCE_NEUTRAL_BASE": 30,
    "ATTACK_INFLUENCE_OWNED_BASE": 40,
    "ATTACK_INFLUENCE_STRATEGIC_MULTIPLIER": 8,
    "CAMPAIGN_STARTING_INFLUENCE": 100,
    "CARAVAN_BASE_GOLD_FEE": 0,
    "CARAVAN_DISTANCE_GOLD_FEE": 2,
    "CARAVAN_HOURS_PER_STEP": 6,
    "CARAVAN_MIN_GOLD_FEE": 1,
    "CARAVAN_VOLUME_GOLD_FEE": 1,
    "CARAVAN_VOLUME_STEP": 10,
    "CLAN_ACTIVITY_MIN_MATCHES": 3,
    "CLAN_ACTIVITY_WINDOW_DAYS": 28,
    "CLAN_ATTACK_COOLDOWN_HOURS": 96,
    "CLAN_ATTACK_SQUAD_MIN_MEMBERS": 5,
    "CLAN_JOIN_TIMEOUT_HOURS": 72,
    "CLAN_LEVEL_1_ATTACK_CAPACITY": 1,
    "CLAN_LEVEL_2_ACTIVE_MEMBERS": 7,
    "CLAN_LEVEL_2_ATTACK_CAPACITY": 2,
    "CLAN_LEVEL_2_INFLUENCE": 150,
    "CLAN_LEVEL_2_TERRITORIES": 1,
    "CLAN_LEVEL_3_ACTIVE_MEMBERS": 10,
    "CLAN_LEVEL_3_ATTACK_CAPACITY": 3,
    "CLAN_LEVEL_3_INFLUENCE": 400,
    "CLAN_LEVEL_3_TERRITORIES": 3,
    "CLAN_LEVEL_4_ACTIVE_MEMBERS": 14,
    "CLAN_LEVEL_4_ATTACK_CAPACITY": 4,
    "CLAN_LEVEL_4_INFLUENCE": 800,
    "CLAN_LEVEL_4_TERRITORIES": 5,
    "CLAN_LEVEL_5_ACTIVE_MEMBERS": 18,
    "CLAN_LEVEL_5_ATTACK_CAPACITY": 5,
    "CLAN_LEVEL_5_INFLUENCE": 1500,
    "CLAN_LEVEL_5_TERRITORIES": 8,
    "ECONOMY_MAX_CATCHUP_DAYS": 56,
    "ECONOMY_TICK_HOURS": 24,
    "ELO_EXPECTED_SCORE_DIVISOR": 400,
    "ELO_PROVISIONAL_K": 40,
    "ELO_PROVISIONAL_MATCHES": 30,
    "ELO_REGULAR_K": 24,
    "ELO_START_RATING": 1000,
    "FLEET_BASE_FOOD_COST": 2,
    "FLEET_BASE_GOLD_COST": 360,
    "FLEET_BASE_IRON_COST": 2,
    "FLEET_BASE_WOOD_COST": 5,
    "FLEET_FOOD_COST_PER_STEP": 1,
    "FLEET_FOOD_LEVEL_DIVISOR": 2,
    "FLEET_GOLD_COST_PER_LEVEL": 130,
    "FLEET_IRON_COST_PER_LEVEL": 1,
    "FLEET_LEVEL_BONUS_PERCENT": 2,
    "FLEET_WOOD_COST_PER_LEVEL": 1,
    "FORTIFICATION_BASE_GOLD_COST": 240,
    "FORTIFICATION_BASE_IRON_COST": 3,
    "FORTIFICATION_GOLD_COST_PER_LEVEL": 80,
    "FORTIFICATION_IRON_COST_PER_LEVEL": 1,
    "FORTIFICATION_MITHRIL_COST_PER_LEVEL": 1,
    "FORTIFICATION_MITHRIL_START_LEVEL": 4,
    "NEUTRAL_CAPTURE_REQUIRED_WINS": 25,
    "OFFENSE_BASE_FOOD_COST": 1,
    "OFFENSE_BASE_GOLD_COST": 260,
    "OFFENSE_BASE_IRON_COST": 2,
    "OFFENSE_FOOD_COST_PER_STEP": 1,
    "OFFENSE_FOOD_LEVEL_DIVISOR": 3,
    "OFFENSE_GOLD_COST_PER_LEVEL": 90,
    "OFFENSE_IRON_COST_PER_LEVEL": 1,
    "POPULATION_BASE_GOLD_COST": 180,
    "POPULATION_BASE_GROWTH_PERCENT": 5,
    "POPULATION_BASE_WOOD_COST": 2,
    "POPULATION_FLAT_GROWTH_PER_LEVEL": 1000,
    "POPULATION_GOLD_COST_PER_LEVEL": 70,
    "POPULATION_GROWTH_RELIC_DIVISOR": 10,
    "POPULATION_MAXIMUM": 1_000_000,
    "POPULATION_WOOD_COST_PER_LEVEL": 1,
    "PORT_BASE_GOLD_COST": 300,
    "PORT_BASE_IRON_COST": 2,
    "PORT_BASE_WOOD_COST": 4,
    "PORT_GOLD_COST_PER_LEVEL": 110,
    "PORT_IRON_COST_PER_STEP": 1,
    "PORT_IRON_LEVEL_DIVISOR": 2,
    "PORT_LEVEL_BONUS_PERCENT": 1,
    "PORT_WOOD_COST_PER_LEVEL": 1,
    "RELIC_LEVEL_1_COST_MULTIPLIER": 1,
    "RELIC_LEVEL_2_COST_MULTIPLIER": 5,
    "RELIC_LEVEL_3_COST_MULTIPLIER": 15,
    "TERRITORY_LEVEL_BONUS_PERCENT": 2,
    "TERRITORY_MAX_UPGRADE_LEVEL": 10,
    "TERRITORY_MAX_UPGRADE_LEVELS_PER_PURCHASE": 3,
    "TERRITORY_MAX_WEEKLY_CATCHUP_CYCLES": 8,
    "TERRITORY_MIN_RESOURCE_OUTPUT": 1,
    "TERRITORY_RESOURCE_PAYOUT_HOURS": 168,
    "TERRITORY_RESOURCE_WEALTH_DIVISOR": 25,
    "WAR_DURATION_HOURS": 96,
    "WAR_ELO_BASE_POINTS": 10,
    "WAR_ELO_DRAW_DIVISOR": 2,
    "WAR_ELO_EXPECTED_WEIGHT": 1.5,
    "WAR_ELO_MAX_DRAW_POINTS": 8,
    "WAR_ELO_MAX_POINTS": 15,
    "WAR_ELO_MIN_DRAW_POINTS": 3,
    "WAR_ELO_MIN_POINTS": 5,
    "WAR_FULL_CLAN_TEAM_BONUS_PERCENT": 10,
    "WAR_MIN_MATCH_DURATION_SECONDS": 120,
    "WAR_MODIFIER_CAP_PERCENT": 35,
    "WAR_POWER_BONUS_CAP_POINTS": 3,
    "WAR_POWER_POINTS_DIVISOR": 5,
    "WAR_TEAM_SIZE_BONUS_STEP_PERCENT": 10,
    "WAR_VICTORY_INFLUENCE_BASE": 25,
    "WAR_VICTORY_STRATEGIC_MULTIPLIER": 5,
}


def upgrade():
    op.create_table(
        "campaign_rule_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_campaign_rule_sets_version",
        "campaign_rule_sets",
        ["version"],
        unique=True,
    )
    op.create_index(
        "uq_campaign_rule_sets_active",
        "campaign_rule_sets",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active IS TRUE"),
        sqlite_where=sa.text("is_active = 1"),
    )

    rule_sets = sa.table(
        "campaign_rule_sets",
        sa.column("version", sa.Integer()),
        sa.column("values", sa.JSON()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_by_user_id", sa.Integer()),
        sa.column("reason", sa.String(length=500)),
    )
    op.bulk_insert(
        rule_sets,
        [
            {
                "version": 1,
                "values": INITIAL_CAMPAIGN_RULE_VALUES,
                "is_active": True,
                "created_by_user_id": None,
                "reason": "initial_effective_defaults",
            }
        ],
    )


def downgrade():
    op.drop_index("uq_campaign_rule_sets_active", table_name="campaign_rule_sets")
    op.drop_index("ix_campaign_rule_sets_version", table_name="campaign_rule_sets")
    op.drop_table("campaign_rule_sets")
