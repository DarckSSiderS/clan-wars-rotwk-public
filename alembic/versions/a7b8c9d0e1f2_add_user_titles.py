"""Добавляет титулы пользователей и их назначения.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
"""

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "titles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("name_en", sa.String(length=120), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("name_de", sa.String(length=120), nullable=True),
        sa.Column("description_de", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_titles_id", "titles", ["id"], unique=False)
    op.create_index("ix_titles_name", "titles", ["name"], unique=True)
    op.create_table(
        "user_titles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title_id", sa.Integer(), nullable=False),
        sa.Column("assigned_by_user_id", sa.Integer(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["title_id"], ["titles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "title_id", name="uq_user_title"),
    )
    op.create_index("ix_user_titles_id", "user_titles", ["id"], unique=False)
    op.create_index("ix_user_titles_title_id", "user_titles", ["title_id"], unique=False)
    op.create_index("ix_user_titles_user_id", "user_titles", ["user_id"], unique=False)


def downgrade():
    op.drop_index("ix_user_titles_user_id", table_name="user_titles")
    op.drop_index("ix_user_titles_title_id", table_name="user_titles")
    op.drop_index("ix_user_titles_id", table_name="user_titles")
    op.drop_table("user_titles")
    op.drop_index("ix_titles_name", table_name="titles")
    op.drop_index("ix_titles_id", table_name="titles")
    op.drop_table("titles")
