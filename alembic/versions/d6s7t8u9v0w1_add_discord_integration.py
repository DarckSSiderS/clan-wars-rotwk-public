"""Palantir account links, resources and delivery journal."""

from alembic import op
import sqlalchemy as sa

revision = "d6s7t8u9v0w1"
down_revision = "c5r6s7t8u9v0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "discord_links",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("discord_user_id", sa.String(20), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "discord_link_codes",
        sa.Column("discord_user_id", sa.String(20), primary_key=True),
        sa.Column("code_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "discord_resources",
        sa.Column("guild_id", sa.String(20), primary_key=True),
        sa.Column("key", sa.String(160), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
    )
    op.create_table(
        "discord_deliveries",
        sa.Column("guild_id", sa.String(20), primary_key=True),
        sa.Column("key", sa.String(200), primary_key=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    for name in (
        "discord_deliveries",
        "discord_resources",
        "discord_link_codes",
        "discord_links",
    ):
        op.drop_table(name)
