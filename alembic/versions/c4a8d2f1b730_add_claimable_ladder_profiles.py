"""add claimable ladder profiles

Revision ID: c4a8d2f1b730
Revises: a12c4d8f9b21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4a8d2f1b730"
down_revision: Union[str, None] = "a12c4d8f9b21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_claimed", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_claimed")
