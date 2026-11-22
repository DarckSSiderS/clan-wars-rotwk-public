"""Добавляет участников командных матчей и параметры командного расчёта.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""

from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    participants = op.create_table(
        "match_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("nickname", sa.String(), nullable=False),
        sa.Column("player_uuid", sa.String(), nullable=True),
        sa.Column("faction", sa.String(), nullable=True),
        sa.Column("faction_index", sa.Integer(), nullable=True),
        sa.Column("team", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_winner", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_observer", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("old_rank", sa.Integer(), nullable=True),
        sa.Column("new_rank", sa.Integer(), nullable=True),
        sa.Column("elo", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("match_id", "nickname", name="uq_match_participant_nickname"),
    )
    op.create_index("ix_match_participants_match_team", "match_participants", ["match_id", "team"])
    op.create_index("ix_match_participants_nickname", "match_participants", ["nickname"])
    op.create_index("ix_match_participants_uuid", "match_participants", ["player_uuid"])

    op.add_column("campaign_settings", sa.Column("replay_cursor_ms", sa.BigInteger(), nullable=True))

    op.add_column("clan_war_match_results", sa.Column("game_mode", sa.String(length=32), nullable=True))
    op.add_column("clan_war_match_results", sa.Column("winner_team_size", sa.Integer(), server_default="1", nullable=False))
    op.add_column("clan_war_match_results", sa.Column("loser_team_size", sa.Integer(), server_default="1", nullable=False))
    op.add_column("clan_war_match_results", sa.Column("winner_clan_members", sa.Integer(), server_default="1", nullable=False))
    op.add_column("clan_war_match_results", sa.Column("loser_clan_members", sa.Integer(), server_default="1", nullable=False))
    op.add_column("clan_war_match_results", sa.Column("winner_team_bonus_percent", sa.Float(), server_default="0", nullable=False))
    op.add_column("clan_war_match_results", sa.Column("winner_team_bonus_points", sa.Float(), server_default="0", nullable=False))
    op.add_column("clan_war_match_results", sa.Column("loser_team_bonus_percent", sa.Float(), server_default="0", nullable=False))
    op.add_column("clan_war_match_results", sa.Column("loser_team_bonus_points", sa.Float(), server_default="0", nullable=False))
    op.execute("UPDATE clan_wars SET scoring_version = 'elo_team_v2' WHERE status = 'active'")

    connection = op.get_bind()
    rows = connection.execute(sa.text(
        """
        SELECT id, winner_player, winner_player_uuid, winner_faction,
               winner_faction_index, winner_old_rank, winner_new_rank, winner_elo,
               loser_player, loser_player_uuid, loser_faction,
               loser_faction_index, loser_old_rank, loser_new_rank, loser_elo
        FROM matches
        """
    )).mappings()
    for row in rows:
        connection.execute(participants.insert(), [
            {
                "match_id": row["id"],
                "nickname": row["winner_player"],
                "player_uuid": row["winner_player_uuid"],
                "faction": row["winner_faction"],
                "faction_index": row["winner_faction_index"],
                "team": 1,
                "is_winner": True,
                "is_observer": False,
                "old_rank": row["winner_old_rank"],
                "new_rank": row["winner_new_rank"],
                "elo": row["winner_elo"],
            },
            {
                "match_id": row["id"],
                "nickname": row["loser_player"],
                "player_uuid": row["loser_player_uuid"],
                "faction": row["loser_faction"],
                "faction_index": row["loser_faction_index"],
                "team": 2,
                "is_winner": False,
                "is_observer": False,
                "old_rank": row["loser_old_rank"],
                "new_rank": row["loser_new_rank"],
                "elo": row["loser_elo"],
            },
        ])


def downgrade():
    for column in (
        "loser_team_bonus_points",
        "loser_team_bonus_percent",
        "winner_team_bonus_points",
        "winner_team_bonus_percent",
        "loser_clan_members",
        "winner_clan_members",
        "loser_team_size",
        "winner_team_size",
        "game_mode",
    ):
        op.drop_column("clan_war_match_results", column)
    op.drop_column("campaign_settings", "replay_cursor_ms")
    op.drop_index("ix_match_participants_uuid", table_name="match_participants")
    op.drop_index("ix_match_participants_nickname", table_name="match_participants")
    op.drop_index("ix_match_participants_match_team", table_name="match_participants")
    op.drop_table("match_participants")
