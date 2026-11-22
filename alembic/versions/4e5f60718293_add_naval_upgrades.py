"""add naval territory upgrades and war route

Revision ID: 4e5f60718293
Revises: 3d4e5f607182
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision = "4e5f60718293"
down_revision = "3d4e5f607182"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "territories",
        sa.Column("port_level", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "territories",
        sa.Column("fleet_level", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "clan_wars",
        sa.Column("attack_route", sa.String(length=16), nullable=False, server_default="land"),
    )
    op.alter_column(
        "clan_war_participants",
        "war_points",
        existing_type=sa.Integer(),
        type_=sa.Float(),
        existing_nullable=True,
        postgresql_using="war_points::double precision",
    )


def downgrade():
    op.alter_column(
        "clan_war_participants",
        "war_points",
        existing_type=sa.Float(),
        type_=sa.Integer(),
        existing_nullable=True,
        postgresql_using="round(war_points)::integer",
    )
    op.drop_column("clan_wars", "attack_route")
    op.drop_column("territories", "fleet_level")
    op.drop_column("territories", "port_level")
