"""add clan attack cooldown

Revision ID: f3b2d7a91c40
Revises: e84c26f9170b
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3b2d7a91c40"
down_revision: Union[str, None] = "e84c26f9170b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clans", sa.Column("next_attack_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("clans", "next_attack_at")
