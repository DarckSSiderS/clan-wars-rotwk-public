"""add protected administrative clan

Revision ID: 3d4e5f607182
Revises: 2c3d4e5f6071
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3d4e5f607182"
down_revision: Union[str, None] = "2c3d4e5f6071"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "clans",
        sa.Column(
            "is_admin_clan",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("clans", "is_admin_clan")
