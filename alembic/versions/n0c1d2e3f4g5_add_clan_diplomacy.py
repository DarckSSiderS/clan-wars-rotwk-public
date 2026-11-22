"""Добавляет отношения и историю дипломатии кланов.

Revision ID: n0c1d2e3f4g5
Revises: m9b0c1d2e3f4
Create Date: 2026-08-26 03:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "n0c1d2e3f4g5"
down_revision = "m9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "clan_diplomatic_relations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clan_low_id", sa.Integer(), nullable=False),
        sa.Column("clan_high_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="neutral"),
        sa.Column("requested_by_clan_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("clan_low_id < clan_high_id", name="ck_clan_diplomatic_pair_order"),
        sa.ForeignKeyConstraint(["clan_low_id"], ["clans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clan_high_id"], ["clans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_clan_id"], ["clans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clan_low_id", "clan_high_id", name="uq_clan_diplomatic_pair"),
    )
    op.create_index("ix_clan_diplomatic_relations_clan_low_id", "clan_diplomatic_relations", ["clan_low_id"])
    op.create_index("ix_clan_diplomatic_relations_clan_high_id", "clan_diplomatic_relations", ["clan_high_id"])
    op.create_index("ix_clan_diplomatic_relations_status", "clan_diplomatic_relations", ["status"])

    op.create_table(
        "clan_diplomacy_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("relation_id", sa.Integer(), nullable=False),
        sa.Column("actor_clan_id", sa.Integer(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("previous_status", sa.String(length=32), nullable=False),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["relation_id"], ["clan_diplomatic_relations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_clan_id"], ["clans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clan_diplomacy_events_relation_id", "clan_diplomacy_events", ["relation_id"])
    op.create_index("ix_clan_diplomacy_events_created_at", "clan_diplomacy_events", ["created_at"])


def downgrade():
    op.drop_index("ix_clan_diplomacy_events_created_at", table_name="clan_diplomacy_events")
    op.drop_index("ix_clan_diplomacy_events_relation_id", table_name="clan_diplomacy_events")
    op.drop_table("clan_diplomacy_events")
    op.drop_index("ix_clan_diplomatic_relations_status", table_name="clan_diplomatic_relations")
    op.drop_index("ix_clan_diplomatic_relations_clan_high_id", table_name="clan_diplomatic_relations")
    op.drop_index("ix_clan_diplomatic_relations_clan_low_id", table_name="clan_diplomatic_relations")
    op.drop_table("clan_diplomatic_relations")
