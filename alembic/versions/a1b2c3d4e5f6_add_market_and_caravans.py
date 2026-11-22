"""Add clan market offers and durable trade caravans.

Revision ID: a1b2c3d4e5f6
Revises: f0a1b2c3d4e5
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "market_offers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("creator_clan_id", sa.Integer(), nullable=False),
        sa.Column("accepted_by_clan_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("accepted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("give_resource", sa.String(length=20), nullable=False),
        sa.Column("give_amount", sa.Integer(), nullable=False),
        sa.Column("receive_resource", sa.String(length=20), nullable=False),
        sa.Column("receive_amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("route", sa.JSON(), nullable=True),
        sa.Column("route_steps", sa.Integer(), nullable=True),
        sa.Column("creator_shipping_cost", sa.Integer(), nullable=True),
        sa.Column("accepter_shipping_cost", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["accepted_by_clan_id"], ["clans.id"]),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["creator_clan_id"], ["clans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_offers_creator_clan_id", "market_offers", ["creator_clan_id"])
    op.create_index("ix_market_offers_accepted_by_clan_id", "market_offers", ["accepted_by_clan_id"])
    op.create_index("ix_market_offers_status", "market_offers", ["status"])
    op.create_index("ix_market_offers_expires_at", "market_offers", ["expires_at"])
    op.create_index("ix_market_offers_eta", "market_offers", ["eta"])
    op.create_index("ix_market_offers_status_created", "market_offers", ["status", "created_at"])

    op.create_table(
        "trade_caravans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("from_clan_id", sa.Integer(), nullable=False),
        sa.Column("to_clan_id", sa.Integer(), nullable=False),
        sa.Column("resource", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("route", sa.JSON(), nullable=False),
        sa.Column("departed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("eta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["from_clan_id"], ["clans.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["market_offers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_clan_id"], ["clans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trade_caravans_offer_id", "trade_caravans", ["offer_id"])
    op.create_index("ix_trade_caravans_status", "trade_caravans", ["status"])
    op.create_index("ix_trade_caravans_eta", "trade_caravans", ["eta"])
    op.create_index("ix_trade_caravans_status_eta", "trade_caravans", ["status", "eta"])


def downgrade():
    op.drop_index("ix_trade_caravans_status_eta", table_name="trade_caravans")
    op.drop_index("ix_trade_caravans_eta", table_name="trade_caravans")
    op.drop_index("ix_trade_caravans_status", table_name="trade_caravans")
    op.drop_index("ix_trade_caravans_offer_id", table_name="trade_caravans")
    op.drop_table("trade_caravans")
    op.drop_index("ix_market_offers_status_created", table_name="market_offers")
    op.drop_index("ix_market_offers_eta", table_name="market_offers")
    op.drop_index("ix_market_offers_expires_at", table_name="market_offers")
    op.drop_index("ix_market_offers_status", table_name="market_offers")
    op.drop_index("ix_market_offers_accepted_by_clan_id", table_name="market_offers")
    op.drop_index("ix_market_offers_creator_clan_id", table_name="market_offers")
    op.drop_table("market_offers")
