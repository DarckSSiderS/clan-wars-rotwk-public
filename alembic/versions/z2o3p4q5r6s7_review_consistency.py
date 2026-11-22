"""Keep market seasons and replay finalization boundaries explicit.

Revision ID: z2o3p4q5r6s7
Revises: y1n2o3p4q5r6
"""
from alembic import op
import sqlalchemy as sa

revision = "z2o3p4q5r6s7"
down_revision = "y1n2o3p4q5r6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("market_offers") as batch:
        batch.add_column(sa.Column("season_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_market_offers_season_id", "campaign_seasons", ["season_id"], ["id"])
        batch.create_index("ix_market_offers_season_id", ["season_id"])
    op.execute(sa.text("""
        UPDATE market_offers SET season_id = (
            SELECT id FROM campaign_seasons WHERE status = 'active'
        ) WHERE status IN ('open', 'in_transit')
    """))
    op.add_column("worker_heartbeats", sa.Column("replay_synced_through_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("worker_heartbeats", "replay_synced_through_at")
    with op.batch_alter_table("market_offers") as batch:
        batch.drop_index("ix_market_offers_season_id")
        batch.drop_constraint("fk_market_offers_season_id", type_="foreignkey")
        batch.drop_column("season_id")
