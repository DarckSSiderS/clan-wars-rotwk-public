"""add external player identities and nickname history

Revision ID: 2c3d4e5f6071
Revises: 1b2c3d4e5f60
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2c3d4e5f6071"
down_revision: Union[str, None] = "1b2c3d4e5f60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "external_player_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("external_uuid", sa.String(length=80), nullable=False),
        sa.Column("current_nickname", sa.String(length=120), nullable=False),
        sa.Column("verification_status", sa.String(length=20), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source",
            "external_uuid",
            name="uq_external_identity_source_uuid",
        ),
        sa.UniqueConstraint(
            "user_id",
            "source",
            name="uq_external_identity_user_source",
        ),
    )
    op.create_index(
        "ix_external_player_identities_user_id",
        "external_player_identities",
        ["user_id"],
    )

    op.create_table(
        "external_player_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("identity_id", sa.Integer(), nullable=False),
        sa.Column("nickname", sa.String(length=120), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["external_player_identities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "identity_id",
            "nickname",
            name="uq_external_identity_alias",
        ),
    )
    op.create_index(
        "ix_external_player_aliases_identity_id",
        "external_player_aliases",
        ["identity_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_external_player_aliases_identity_id",
        table_name="external_player_aliases",
    )
    op.drop_table("external_player_aliases")
    op.drop_index(
        "ix_external_player_identities_user_id",
        table_name="external_player_identities",
    )
    op.drop_table("external_player_identities")
