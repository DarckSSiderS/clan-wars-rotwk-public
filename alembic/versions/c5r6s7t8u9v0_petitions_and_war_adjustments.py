"""Petitions, votes, ranked comments and auditable war score adjustments."""
from alembic import op
import sqlalchemy as sa

revision = "c5r6s7t8u9v0"
down_revision = "b4q5r6s7t8u9"
branch_labels = None
depends_on = None


def ref(name, target, nullable=False, ondelete="CASCADE"):
    return sa.Column(name, sa.Integer(), sa.ForeignKey(target, ondelete=ondelete), nullable=nullable)


def created():
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade():
    op.create_table("petitions", sa.Column("id", sa.Integer(), primary_key=True),
        ref("author_id", "users.id", True, "SET NULL"), sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False), sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False), created())
    op.create_table("petition_votes", sa.Column("id", sa.Integer(), primary_key=True),
        ref("petition_id", "petitions.id"), ref("user_id", "users.id"), sa.Column("option_index", sa.Integer(), nullable=False),
        sa.UniqueConstraint("petition_id", "user_id", name="uq_petition_user_vote"))
    op.create_table("petition_comments", sa.Column("id", sa.Integer(), primary_key=True),
        ref("petition_id", "petitions.id"), ref("author_id", "users.id", True, "SET NULL"),
        sa.Column("body", sa.Text(), nullable=False), created())
    op.create_table("petition_reactions", sa.Column("id", sa.Integer(), primary_key=True),
        ref("comment_id", "petition_comments.id"), ref("user_id", "users.id"), sa.Column("value", sa.Integer(), nullable=False),
        sa.UniqueConstraint("comment_id", "user_id", name="uq_petition_comment_reaction"),
        sa.CheckConstraint("value IN (-1, 1)", name="ck_petition_reaction_value"))
    op.create_table("war_score_adjustments", sa.Column("id", sa.Integer(), primary_key=True),
        ref("war_id", "clan_wars.id"), ref("clan_id", "clans.id"), ref("actor_id", "users.id", True, "SET NULL"),
        sa.Column("request_id", sa.String(36), nullable=False, unique=True),
        sa.Column("points", sa.Float(), nullable=False), sa.Column("reason", sa.Text(), nullable=False), created())
    for table, column in [("petition_votes", "petition_id"), ("petition_comments", "petition_id"), ("petition_reactions", "comment_id"), ("war_score_adjustments", "war_id")]:
        op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    for table in ("war_score_adjustments", "petition_reactions", "petition_comments", "petition_votes", "petitions"):
        op.drop_table(table)
