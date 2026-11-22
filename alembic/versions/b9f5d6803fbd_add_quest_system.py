"""add_quest_system

Revision ID: b9f5d6803fbd
Revises: 95bd14acbdfd
Create Date: 2025-08-28 03:02:39.248608

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9f5d6803fbd'
down_revision: Union[str, None] = '95bd14acbdfd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    quest_type = sa.Enum("DAILY", "WEEKLY", name="questtype")
    quest_category = sa.Enum(
        "WINS",
        "MATCHES_PLAYED",
        "FACTION_WINS",
        "STREAK",
        name="questcategory",
    )
    op.create_table(
        "quests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quest_type", quest_type, nullable=False),
        sa.Column("category", quest_category, nullable=False),
        sa.Column("target_value", sa.Integer(), nullable=False),
        sa.Column("reward_coins", sa.Integer(), nullable=False),
        sa.Column("reward_experience", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quests_id", "quests", ["id"])
    op.create_table(
        "user_quests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("quest_id", sa.Integer(), nullable=False),
        sa.Column("current_progress", sa.Integer(), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=True),
        sa.Column("is_claimed", sa.Boolean(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["quest_id"], ["quests.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_quests_id", "user_quests", ["id"])


def downgrade() -> None:
    op.drop_index("ix_user_quests_id", table_name="user_quests")
    op.drop_table("user_quests")
    op.drop_index("ix_quests_id", table_name="quests")
    op.drop_table("quests")
    sa.Enum(name="questcategory").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="questtype").drop(op.get_bind(), checkfirst=True)
