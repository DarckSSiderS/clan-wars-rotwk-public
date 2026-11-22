"""Добавляет личные диалоги, блокировки и жалобы.

Revision ID: o1d2e3f4g5h6
Revises: n0c1d2e3f4g5
Create Date: 2026-08-26 04:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "o1d2e3f4g5h6"
down_revision = "n0c1d2e3f4g5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "direct_conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_low_id", sa.Integer(), nullable=False),
        sa.Column("user_high_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("user_low_id < user_high_id", name="ck_direct_conversation_pair_order"),
        sa.ForeignKeyConstraint(["user_low_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_high_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_low_id", "user_high_id", name="uq_direct_conversation_pair"),
    )
    op.create_index("ix_direct_conversations_user_low_id", "direct_conversations", ["user_low_id"])
    op.create_index("ix_direct_conversations_user_high_id", "direct_conversations", ["user_high_id"])
    op.create_index("ix_direct_conversations_updated_at", "direct_conversations", ["updated_at"])

    op.create_table(
        "direct_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["direct_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_direct_messages_conversation_id", "direct_messages", ["conversation_id"])
    op.create_index("ix_direct_messages_sender_id", "direct_messages", ["sender_id"])
    op.create_index("ix_direct_messages_created_at", "direct_messages", ["created_at"])
    op.create_index("ix_direct_messages_read_at", "direct_messages", ["read_at"])

    op.create_table(
        "user_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("blocker_id", sa.Integer(), nullable=False),
        sa.Column("blocked_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("blocker_id != blocked_id", name="ck_user_block_not_self"),
        sa.ForeignKeyConstraint(["blocker_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blocked_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_user_block_pair"),
    )
    op.create_index("ix_user_blocks_blocker_id", "user_blocks", ["blocker_id"])
    op.create_index("ix_user_blocks_blocked_id", "user_blocks", ["blocked_id"])

    op.create_table(
        "direct_message_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("reporter_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["direct_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "reporter_id", name="uq_direct_message_reporter"),
    )
    op.create_index("ix_direct_message_reports_message_id", "direct_message_reports", ["message_id"])
    op.create_index("ix_direct_message_reports_reporter_id", "direct_message_reports", ["reporter_id"])
    op.create_index("ix_direct_message_reports_status", "direct_message_reports", ["status"])
    op.create_index("ix_direct_message_reports_created_at", "direct_message_reports", ["created_at"])


def downgrade():
    op.drop_index("ix_direct_message_reports_created_at", table_name="direct_message_reports")
    op.drop_index("ix_direct_message_reports_status", table_name="direct_message_reports")
    op.drop_index("ix_direct_message_reports_reporter_id", table_name="direct_message_reports")
    op.drop_index("ix_direct_message_reports_message_id", table_name="direct_message_reports")
    op.drop_table("direct_message_reports")
    op.drop_index("ix_user_blocks_blocked_id", table_name="user_blocks")
    op.drop_index("ix_user_blocks_blocker_id", table_name="user_blocks")
    op.drop_table("user_blocks")
    op.drop_index("ix_direct_messages_read_at", table_name="direct_messages")
    op.drop_index("ix_direct_messages_created_at", table_name="direct_messages")
    op.drop_index("ix_direct_messages_sender_id", table_name="direct_messages")
    op.drop_index("ix_direct_messages_conversation_id", table_name="direct_messages")
    op.drop_table("direct_messages")
    op.drop_index("ix_direct_conversations_updated_at", table_name="direct_conversations")
    op.drop_index("ix_direct_conversations_user_high_id", table_name="direct_conversations")
    op.drop_index("ix_direct_conversations_user_low_id", table_name="direct_conversations")
    op.drop_table("direct_conversations")
