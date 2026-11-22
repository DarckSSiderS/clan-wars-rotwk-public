"""Add frozen public season archives without reconstructing historical data."""

from alembic import op
import sqlalchemy as sa


revision = "t2h3i4j5k6l7"
down_revision = "s1g2h3i4j5k6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "campaign_season_archives",
        sa.Column("season_id", sa.Integer(), sa.ForeignKey("campaign_seasons.id"), primary_key=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("map_svg", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
    )


def downgrade():
    op.drop_table("campaign_season_archives")
