"""add war influence cost

Revision ID: d7b5e91a2c44
Revises: c4a8d2f1b730
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7b5e91a2c44"
down_revision: Union[str, None] = "c4a8d2f1b730"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clan_wars", sa.Column("influence_cost", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("clan_wars", "influence_cost")
