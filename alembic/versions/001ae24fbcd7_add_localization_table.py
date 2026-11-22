"""Add localization table

Revision ID: 001ae24fbcd7
Revises: 66a3b62aa507
Create Date: 2025-08-25 19:01:00.608084

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001ae24fbcd7'
down_revision: Union[str, None] = '66a3b62aa507'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "localizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("identifier", sa.String(length=255), nullable=False),
        sa.Column("ru", sa.Text(), nullable=False),
        sa.Column("eng", sa.Text(), nullable=False),
        sa.Column("webpage", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_localizations_id", "localizations", ["id"])
    op.create_index(
        "ix_localizations_identifier",
        "localizations",
        ["identifier"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_localizations_identifier", table_name="localizations")
    op.drop_index("ix_localizations_id", table_name="localizations")
    op.drop_table("localizations")
