"""Add one-time clan map color.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""

from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("clans", sa.Column("map_color", sa.String(length=7), nullable=True))
    op.create_unique_constraint("uq_clans_map_color", "clans", ["map_color"])


def downgrade():
    op.drop_constraint("uq_clans_map_color", "clans", type_="unique")
    op.drop_column("clans", "map_color")
