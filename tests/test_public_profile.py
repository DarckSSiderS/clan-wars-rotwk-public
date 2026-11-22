import asyncio
from datetime import datetime, timezone

from app.api.v1 import users as users_api
from app.api.v1.users import (
    get_all_user_matches,
    get_player_statistics,
    get_public_profile_overview,
    get_user_clan,
)
from app.models.clan import Clan, ClanMember
from app.models.external_identity import ExternalPlayerAlias, ExternalPlayerIdentity
from app.models.match import Match, MatchParticipant
from app.models.user import User
from app.services.map_preview_storage_service import MapPreviewStorageService


def test_public_arena_nickname_resolves_collision_safe_internal_username(db):
    legacy_user = User(
        username="fatcat",
        display_name="fatcat",
        email="legacy-fatcat@example.test",
        hashed_password="unused",
        is_claimed=True,
    )
    arena_user = User(
        username="fatcat~367fb5b7",
        display_name="fatcat",
        email="arena-fatcat@example.test",
        hashed_password="unused",
        is_claimed=True,
    )
    db.add_all([legacy_user, arena_user])
    db.flush()
    identity = ExternalPlayerIdentity(
        user_id=arena_user.id,
        source="bfmeladder",
        external_uuid="arena-fatcat-uuid",
        current_nickname="fatcat",
        verification_status="verified",
    )
    db.add(identity)
    db.flush()
    db.add(ExternalPlayerAlias(identity_id=identity.id, nickname="fatcat"))
    db.commit()

    result = asyncio.run(get_public_profile_overview("fatcat", db))

    assert result["user"]["id"] == arena_user.id
    assert result["user"]["username"] == "fatcat~367fb5b7"
    assert result["user"]["display_name"] == "fatcat"


def test_public_profile_supports_team_match_participants(db, tmp_path, monkeypatch):
    preview_storage = MapPreviewStorageService(tmp_path)
    preview_storage.target_path("Pinnath Gelin").write_bytes(b"\x89PNG\r\n\x1a\npreview")
    monkeypatch.setattr(users_api, "map_preview_storage", preview_storage)
    user = User(
        username="TeamPlayer",
        email="team-player@example.test",
        hashed_password="unused",
        balance=500,
    )
    match = Match(
        match_id="team-profile-match",
        winner_player="TeamPlayer",
        winner_faction="Люди",
        loser_player="EnemyOne",
        loser_faction="Мордор",
        match_date=datetime(2026, 8, 1, 12, 0),
        rating_patch_family="ennorath",
        gamemode_name="2 versus 2",
        map_name="Pinnath Gelin",
    )
    match.participants = [
        MatchParticipant(
            nickname="TeamPlayer",
            faction="Люди",
            team=1,
            is_winner=True,
            elo=1250,
        ),
        MatchParticipant(
            nickname="AllyPlayer",
            faction="Эльфы",
            team=1,
            is_winner=True,
            elo=1200,
        ),
        MatchParticipant(
            nickname="EnemyOne",
            faction="Мордор",
            team=2,
            is_winner=False,
            elo=1150,
        ),
        MatchParticipant(
            nickname="EnemyTwo",
            faction="Изенгард",
            team=2,
            is_winner=False,
            elo=1100,
        ),
    ]
    older_match = Match(
        match_id="team-profile-older-match",
        winner_player="EnemyThree",
        winner_faction="Ангмар",
        loser_player="TeamPlayer",
        loser_faction="Люди",
        match_date=datetime(2026, 7, 30, 12, 0),
        ratings_captured_at=datetime(2026, 7, 30, 12, 5, tzinfo=timezone.utc),
        rating_patch_family="patch_202",
        gamemode_name="1 versus 1",
        map_name="Fords of Isen",
    )
    older_match.participants = [
        MatchParticipant(
            nickname="EnemyThree",
            faction="Ангмар",
            team=1,
            is_winner=True,
            elo=1300,
        ),
        MatchParticipant(
            nickname="TeamPlayer",
            faction="Люди",
            team=2,
            is_winner=False,
            elo=1240,
        ),
    ]
    db.add_all([user, match, older_match])
    db.commit()

    result = asyncio.run(get_public_profile_overview("TeamPlayer", db))
    matches = asyncio.run(get_all_user_matches("TeamPlayer", db))

    assert result["user"]["username"] == "TeamPlayer"
    assert "email" not in result["user"]
    assert "balance" not in result["user"]
    assert result["user"]["player_statistics"]["total_matches"] == 2
    assert result["user"]["player_statistics"]["wins"] == 1
    assert result["user"]["player_statistics"]["recent_matches"][0]["game_mode"] == "2 versus 2"
    assert result["user"]["player_statistics"]["recent_matches"][0]["elo"] == 1250
    assert result["user"]["player_statistics"]["recent_matches"][0]["rating_patch_family"] == "ennorath"
    assert result["statistics"]["maps_played"]["Pinnath Gelin"]["map_preview_url"].startswith(
        "/api/v1/statistics/map-previews/"
    )
    assert matches[0]["map_preview_url"].startswith("/api/v1/statistics/map-previews/")


def test_empty_player_statistics_are_a_valid_zero_state(db):
    user = User(
        username="NewPlayer",
        email="new-player@example.test",
        hashed_password="unused",
    )
    db.add(user)
    db.commit()

    result = asyncio.run(get_player_statistics(user.username, db))

    assert result["total_matches"] == 0
    assert result["recent_matches"] == []
    assert result["elo_history"] == {"patch_202": [], "ennorath": []}


def test_public_user_clan_exposes_actual_membership_role(db):
    leader = User(
        username="ClanLeader",
        email="clan-leader@example.test",
        hashed_password="unused",
    )
    warlord = User(
        username="ClanWarlord",
        email="clan-warlord@example.test",
        hashed_password="unused",
    )
    db.add_all([leader, warlord])
    db.flush()
    clan = Clan(name="Role Clan", leader_id=leader.id)
    db.add(clan)
    db.flush()
    db.add_all([
        ClanMember(user_id=leader.id, clan_id=clan.id, rank="Глава клана"),
        ClanMember(
            user_id=warlord.id,
            clan_id=clan.id,
            rank="Воин",
            is_warlord=True,
        ),
    ])
    db.commit()

    leader_payload = get_user_clan(leader.id, db)
    warlord_payload = get_user_clan(warlord.id, db)

    assert leader_payload["leader_id"] == leader.id
    assert leader_payload["member_rank"] == "Глава клана"
    assert leader_payload["joined_at"] is not None
    assert leader_payload["is_warlord"] is False
    assert warlord_payload["leader_id"] == leader.id
    assert warlord_payload["member_rank"] == "Воин"
    assert warlord_payload["is_warlord"] is True
