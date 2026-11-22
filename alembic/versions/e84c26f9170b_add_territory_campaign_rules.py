"""add territory campaign rules

Revision ID: e84c26f9170b
Revises: d7b5e91a2c44
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e84c26f9170b"
down_revision: Union[str, None] = "d7b5e91a2c44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("territories", sa.Column("is_playable", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("territories", sa.Column("is_coastal", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("territories", sa.Column("has_port", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("territories", sa.Column("required_territories", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("territories", sa.Column("stronghold_power", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    for column in ("stronghold_power", "required_territories", "has_port", "is_coastal", "is_playable"):
        op.drop_column("territories", column)
