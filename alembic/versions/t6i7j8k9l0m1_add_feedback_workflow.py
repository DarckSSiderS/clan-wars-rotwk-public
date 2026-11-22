"""Add user feedback workflow.

Revision ID: t6i7j8k9l0m1
Revises: s5h6i7j8k9l0
Create Date: 2026-08-30
"""

from alembic import op
import sqlalchemy as sa


revision = "t6i7j8k9l0m1"
down_revision = "s5h6i7j8k9l0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "feedback_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reporter_id", sa.Integer(), nullable=False),
        sa.Column("assigned_admin_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reproduction_steps", sa.Text(), nullable=True),
        sa.Column("expected_result", sa.Text(), nullable=True),
        sa.Column("actual_result", sa.Text(), nullable=True),
        sa.Column("attachment_url", sa.String(length=500), nullable=True),
        sa.Column("source_path", sa.String(length=500), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="new"),
        sa.Column("priority", sa.String(length=24), nullable=False, server_default="normal"),
        sa.Column("admin_unread", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_admin_id"], ["users.id"], ondelete="SET NULL"),
    )
    for column in (
        "reporter_id",
        "assigned_admin_id",
        "category",
        "status",
        "priority",
        "admin_unread",
        "created_at",
        "updated_at",
    ):
        op.create_index(f"ix_feedback_tickets_{column}", "feedback_tickets", [column])

    op.create_table(
        "feedback_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["ticket_id"], ["feedback_tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
    )
    for column in ("ticket_id", "author_id", "created_at"):
        op.create_index(f"ix_feedback_messages_{column}", "feedback_messages", [column])


def downgrade():
    op.drop_table("feedback_messages")
    op.drop_table("feedback_tickets")
