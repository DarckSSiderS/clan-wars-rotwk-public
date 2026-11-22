"""Добавляет OAuth-состояния, серверные сессии и поля первичной настройки."""

from alembic import op
import sqlalchemy as sa


revision = "p2e3f4g5h6i7"
down_revision = "o1d2e3f4g5h6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "email",
            existing_type=sa.String(),
            nullable=True,
        )
        batch_op.add_column(
            sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("history_mode", sa.String(length=40), nullable=True))
        batch_op.add_column(
            sa.Column("statistics_started_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.create_table(
        "oauth_login_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("flow_hash", sa.String(length=64), nullable=False),
        sa.Column("return_to", sa.String(length=500), nullable=False, server_default="/"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("state_hash", name="uq_oauth_login_states_state_hash"),
    )
    op.create_index("ix_oauth_login_states_id", "oauth_login_states", ["id"], unique=False)
    op.create_index("ix_oauth_login_states_flow_hash", "oauth_login_states", ["flow_hash"], unique=False)

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_impersonation",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("impersonated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["impersonated_by_user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
    )
    op.create_index("ix_user_sessions_id", "user_sessions", ["id"], unique=False)
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"], unique=False)
    op.create_index(
        "ix_user_sessions_impersonated_by_user_id",
        "user_sessions",
        ["impersonated_by_user_id"],
        unique=False,
    )

    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_security_audit_events_id", "security_audit_events", ["id"], unique=False)
    op.create_index("ix_security_audit_events_user_id", "security_audit_events", ["user_id"], unique=False)
    op.create_index("ix_security_audit_events_actor_user_id", "security_audit_events", ["actor_user_id"], unique=False)
    op.create_index("ix_security_audit_events_event_type", "security_audit_events", ["event_type"], unique=False)


def downgrade():
    op.drop_index("ix_security_audit_events_event_type", table_name="security_audit_events")
    op.drop_index("ix_security_audit_events_actor_user_id", table_name="security_audit_events")
    op.drop_index("ix_security_audit_events_user_id", table_name="security_audit_events")
    op.drop_index("ix_security_audit_events_id", table_name="security_audit_events")
    op.drop_table("security_audit_events")

    op.drop_index("ix_user_sessions_impersonated_by_user_id", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_index("ix_user_sessions_id", table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_index("ix_oauth_login_states_flow_hash", table_name="oauth_login_states")
    op.drop_index("ix_oauth_login_states_id", table_name="oauth_login_states")
    op.drop_table("oauth_login_states")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("statistics_started_at")
        batch_op.drop_column("history_mode")
        batch_op.drop_column("onboarding_completed_at")
