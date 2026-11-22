"""Remaining opt-in cycle startup, income, transit and reinforcement tables."""

from alembic import op
import sqlalchemy as sa

revision = "j2y3z4a5b6c7"
down_revision = "i1x2y3z4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cycle_market_offers",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("season_id", sa.Integer(), sa.ForeignKey("campaign_seasons.id"), nullable=False),
        sa.Column("sender_clan_id", sa.Integer(), sa.ForeignKey("clans.id"), nullable=False),
        sa.Column("target_clan_id", sa.Integer(), sa.ForeignKey("clans.id"), nullable=True),
        sa.Column("accepter_clan_id", sa.Integer(), sa.ForeignKey("clans.id"), nullable=True),
        sa.Column("offered", sa.JSON(), nullable=False),
        sa.Column("requested", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("first_full_cycle", sa.Integer(), nullable=False),
        sa.Column("expires_after_cycle", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_table(
        "cycle_market_caravans",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("cycle_market_offers.id"), nullable=False),
        sa.Column("recipient_clan_id", sa.Integer(), sa.ForeignKey("clans.id"), nullable=False),
        sa.Column("cargo", sa.JSON(), nullable=False),
        sa.Column("route", sa.JSON(), nullable=False),
        sa.Column("departed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arrives_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.UniqueConstraint("offer_id", "recipient_clan_id", name="uq_cycle_market_caravan"),
    )
    op.create_table(
        "cycle_market_commands",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("season_id", sa.Integer(), sa.ForeignKey("campaign_seasons.id"), nullable=False),
        sa.Column("command_id", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.UniqueConstraint("season_id", "command_id", name="uq_cycle_market_command"),
    )
    op.create_table(
        "cycle_territory_profiles",
        sa.Column("season_id", sa.Integer(), sa.ForeignKey("campaign_seasons.id", ondelete="RESTRICT"), primary_key=True, nullable=False),
        sa.Column("territory_id", sa.Integer(), sa.ForeignKey("territories.id", ondelete="RESTRICT"), primary_key=True, nullable=False),
        sa.Column("base", sa.JSON(), nullable=False),
        sa.Column("profile_material", sa.String(length=16), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("profile_material IS NULL OR profile_material IN ('iron','wood','food','mithril')", name="ck_cycle_income_profile_material"),
        sa.CheckConstraint("revision > 0", name="ck_cycle_income_profile_revision"),
    )
    op.create_table(
        "cycle_income_accruals",
        sa.Column("state_id", sa.Integer(), sa.ForeignKey("cycle_economy_states.id", ondelete="RESTRICT"), primary_key=True, nullable=False),
        sa.Column("accrued_through", sa.DateTime(timezone=True), nullable=False),
        sa.Column("residuals", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_cycle_income_accrual_revision"),
    )
    op.create_table(
        "cycle_startups",
        sa.Column("season_id", sa.Integer(), sa.ForeignKey("campaign_seasons.id", ondelete="RESTRICT"), primary_key=True, nullable=False),
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("campaign_cycles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("initial_owners", sa.JSON(), nullable=False),
        sa.Column("initialized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "cycle_startup_clans",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("season_id", sa.Integer(), sa.ForeignKey("cycle_startups.season_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("clan_id", sa.Integer(), sa.ForeignKey("clans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("initial_owned", sa.JSON(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=True),
        sa.Column("qualified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("selected_four", sa.JSON(), nullable=False),
        sa.Column("selected_lands", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.UniqueConstraint("season_id", "clan_id", name="uq_cycle_startup_clan"),
        sa.UniqueConstraint("season_id", "slot", name="uq_cycle_startup_slot"),
        sa.CheckConstraint("revision > 0", name="ck_cycle_startup_revision"),
        sa.CheckConstraint("slot IS NULL OR (slot >= 1 AND slot <= 6)", name="ck_cycle_startup_slot"),
    )
    op.create_table(
        "cycle_startup_identities",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("season_id", sa.Integer(), sa.ForeignKey("cycle_startups.season_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("clan_id", sa.Integer(), sa.ForeignKey("clans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("external_uuid", sa.String(length=80), nullable=False),
        sa.UniqueConstraint("season_id", "source", "external_uuid", name="uq_cycle_startup_identity"),
    )
    op.create_table(
        "cycle_reinforcement_states",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("campaign_cycles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("cycle_id", name="uq_cycle_reinforcement_state_cycle"),
        sa.CheckConstraint("revision > 0", name="ck_cycle_reinforcement_state_revision"),
    )


def downgrade():
    op.drop_table("cycle_reinforcement_states")
    op.drop_table("cycle_startup_identities")
    op.drop_table("cycle_startup_clans")
    op.drop_table("cycle_startups")
    op.drop_table("cycle_income_accruals")
    op.drop_table("cycle_territory_profiles")
    op.drop_table("cycle_market_commands")
    op.drop_table("cycle_market_caravans")
    op.drop_table("cycle_market_offers")
