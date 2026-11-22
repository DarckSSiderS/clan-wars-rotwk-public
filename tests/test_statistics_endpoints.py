import asyncio
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import event

from app.api.v1.statistics import (
    get_clan_statistics,
    get_match_detail,
    get_matches,
    get_overall_statistics,
    get_player_ratings,
    download_match_replay,
)
from app.config import settings
from app.models.clan import Clan, ClanMember
from app.models.match import Match, MatchParticipant
from app.models.external_identity import ExternalPlayerAlias, ExternalPlayerIdentity
from app.models.territory import Territory
from app.models.user import User
from app.models.war import ClanWar


def _add_match(
    db,
    match_id,
    winner,
    winner_faction,
    loser,
    loser_faction,
    match_date=datetime(2026, 7, 30, 12, 0),
    **match_fields,
):
    db.add(
        Match(
            match_id=match_id,
            winner_player=winner,
            winner_faction=winner_faction,
            loser_player=loser,
            loser_faction=loser_faction,
            match_date=match_date,
            **match_fields,
        )
    )


def test_overall_statistics_split_popular_factions_by_patch(db):
    viewer = User(
        id=1,
        username="Viewer",
        email="viewer@example.test",
        hashed_password="unused",
        is_claimed=True,
    )
    db.add(viewer)
    db.add_all([
        Clan(name="Активный клан"),
        Clan(name="Архивный клан", is_deleted=True),
    ])

    ennorath = Match(
        match_id="ennorath-factions",
        winner_player="GondorPlayer",
        winner_faction="Gondor",
        loser_player="MordorPlayer",
        loser_faction="Мордор",
        match_date=datetime(2026, 7, 30, 12, 0),
        rating_patch_family="ennorath",
    )
    ennorath.participants = [
        MatchParticipant(
            nickname="GondorPlayer",
            faction="Gondor",
            team=1,
            is_winner=True,
        ),
        MatchParticipant(
            nickname="MordorPlayer",
            faction="Мордор",
            team=2,
            is_winner=False,
        ),
    ]
    legacy_patch_202 = Match(
        match_id="patch-202-legacy-factions",
        winner_player="MenPlayer",
        winner_faction="Men",
        loser_player="GoblinPlayer",
        loser_faction="Goblins",
        match_date=datetime(2026, 7, 30, 13, 0),
        rating_patch_family="patch_202",
    )
    wrong_family_faction = Match(
        match_id="wrong-family-faction",
        winner_player="RhunPlayer",
        winner_faction="Рун",
        loser_player="AngmarPlayer",
        loser_faction="Ангмар",
        match_date=datetime(2026, 7, 30, 14, 0),
        rating_patch_family="patch_202",
    )
    db.add_all([ennorath, legacy_patch_202, wrong_family_faction])
    db.commit()

    result = asyncio.run(get_overall_statistics(current_user=viewer, db=db))

    by_patch = result["popular_factions_by_patch"]
    ennorath_counts = {item["faction"]: item["count"] for item in by_patch["ennorath"]}
    patch_202_counts = {item["faction"]: item["count"] for item in by_patch["patch_202"]}

    assert set(ennorath_counts) == {
        "Гондор",
        "Арнор",
        "Рохан",
        "Лотлориэн",
        "Имладрис",
        "Гномы",
        "Изенгард",
        "Мордор",
        "Мглистые Горы",
        "Ангмар",
        "Харад",
        "Рун",
    }
    assert set(patch_202_counts) == {
        "Люди",
        "Эльфы",
        "Гномы",
        "Изенгард",
        "Мордор",
        "Гоблины",
        "Ангмар",
    }
    assert ennorath_counts["Гондор"] == 1
    assert ennorath_counts["Мордор"] == 1
    assert ennorath_counts["Арнор"] == 0
    assert patch_202_counts["Люди"] == 1
    assert patch_202_counts["Гоблины"] == 1
    assert patch_202_counts["Ангмар"] == 1
    assert "Рун" not in patch_202_counts
    mixed_counts = {
        item["faction"]: item["count"]
        for item in result["popular_factions"]
    }
    assert mixed_counts["Gondor"] == 1
    assert mixed_counts["Мордор"] == 1
    assert result["total_clans"] == 1


def test_clan_statistics_use_fixed_number_of_queries(db):
    players = [
        User(
            id=index,
            username=f"Player{index}",
            email=f"player{index}@example.test",
            hashed_password="unused",
        )
        for index in range(1, 7)
    ]
    db.add_all(players)
    db.flush()

    clans = [
        Clan(
            id=10,
            name="Первый клан",
            leader_id=players[0].id,
            territory_points=900,
        ),
        Clan(
            id=11,
            name="Второй клан",
            leader_id=players[3].id,
            territory_points=300,
        ),
    ]
    db.add_all(clans)
    db.flush()
    db.add_all(
        [
            ClanMember(
                user_id=player.id,
                clan_id=clans[index // 3].id,
                joined_at=datetime(2026, 7, 1, 0, 0),
            )
            for index, player in enumerate(players)
        ]
    )
    db.add_all(
        [
            Territory(
                id=1,
                name="Земля первого клана",
                region="Тест",
                svg_path_data="M 0 0",
                owner_clan_id=clans[0].id,
            ),
            Territory(
                id=2,
                name="Земля второго клана",
                region="Тест",
                svg_path_data="M 1 1",
                owner_clan_id=clans[1].id,
            ),
        ]
    )
    db.add_all(
        [
            ClanWar(
                territory_id=1,
                attacking_clan_id=clans[1].id,
                defending_clan_id=clans[0].id,
                winner_clan_id=clans[0].id,
                war_type="territory_attack",
                status="completed",
            ),
            ClanWar(
                territory_id=2,
                attacking_clan_id=clans[0].id,
                defending_clan_id=clans[1].id,
                winner_clan_id=clans[1].id,
                war_type="territory_attack",
                status="completed",
            ),
        ]
    )
    _add_match(db, "match-1", "Player1", "Люди", "Player4", "Мордор")
    _add_match(db, "match-2", "Player2", "Эльфы", "Player5", "Гоблины")
    _add_match(
        db,
        "match-before-membership",
        "Player4",
        "Мордор",
        "Player1",
        "Люди",
        match_date=datetime(2026, 6, 30, 12, 0),
    )
    db.commit()

    select_queries = []

    def count_selects(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            select_queries.append(statement)

    event.listen(db.bind, "before_cursor_execute", count_selects)
    try:
        result = asyncio.run(get_clan_statistics(current_user=players[0], db=db))
    finally:
        event.remove(db.bind, "before_cursor_execute", count_selects)

    assert len(result["clans"]) == 2
    assert len(select_queries) <= 5
    assert result["clans"][0]["id"] == clans[0].id
    assert result["clans"][0]["influence"] == 900
    assert result["clans"][0]["wins"] == 2
    assert result["clans"][0]["losses"] == 0
    assert result["clans"][0]["territory_count"] == 1
    assert result["clans"][0]["defenses_won"] == 1
    assert result["clans"][0]["wars_lost"] == 1


def test_match_statistics_support_multiple_factions_and_inclusive_end_date(db):
    player = User(
        id=1,
        username="Player",
        email="player@example.test",
        hashed_password="unused",
    )
    db.add(player)
    _add_match(db, "match-1", "Player", "Люди", "Enemy1", "Мордор")
    _add_match(db, "match-2", "Player", "Эльфы", "Enemy2", "Гоблины")
    _add_match(db, "match-3", "Enemy3", "Изенгард", "Enemy4", "Ангмар")
    db.commit()

    result = asyncio.run(
        get_matches(
            page=1,
            limit=25,
            faction="Люди,Эльфы",
            player=None,
            patch=None,
            game_mode=None,
            date_from="2026-07-30",
            date_to="2026-07-30",
            current_user=player,
            db=db,
        )
    )

    assert result["total_matches"] == 2
    assert {match["id"] for match in result["matches"]} == {1, 2}


def test_match_statistics_filter_by_patch_and_team_size(db):
    player = User(
        id=1,
        username="Player",
        email="player@example.test",
        hashed_password="unused",
    )
    db.add(player)
    _add_match(
        db,
        "ennorath-2v2",
        "Player",
        "Люди",
        "Enemy1",
        "Мордор",
        gamemode_name="2 versus 2",
        game_mode="2 vs 2",
        patch_name="Ennorath",
        rating_patch_family="ennorath",
    )
    _add_match(
        db,
        "patch-202-3v3",
        "Player",
        "Эльфы",
        "Enemy2",
        "Гоблины",
        gamemode_name="3 versus 3",
        game_mode="3 vs 3",
        patch_name="Patch 2.02",
        rating_patch_family="patch_202",
    )
    db.commit()

    result = asyncio.run(
        get_matches(
            page=1,
            limit=25,
            faction=None,
            player=None,
            patch="ennorath",
            game_mode="2v2",
            date_from=None,
            date_to=None,
            current_user=player,
            db=db,
        )
    )

    assert result["total_matches"] == 1
    assert result["matches"][0]["game_mode"] == "2 versus 2"
    assert result["matches"][0]["rating_patch_family"] == "ennorath"


def test_match_detail_exposes_arena_metadata_and_archived_replay(db, tmp_path, monkeypatch):
    viewer = User(
        id=1,
        username="Viewer",
        email="viewer@example.test",
        hashed_password="unused",
    )
    match = Match(
        match_id="detailed-match.BfME2Replay",
        winner_player="Winner",
        winner_faction="Гондор",
        loser_player="Loser",
        loser_faction="Мордор",
        match_date=datetime(2026, 8, 31, 20, 0),
        duration="00:14:20",
        map_name="Fords of Isen",
        map_id="map-1",
        game_name="RotWK",
        gamemode_name="1 versus 1",
        arena_id="arena-1",
        patch_id="ennorath-1.9.7.7d",
        patch_name="Ennorath (1.9.7.7d)",
        patch_version="Ennorath (1.9.7.7d)",
        rating_patch_family="ennorath",
        elo_delta=12,
        downloads=7,
        likes=json.dumps(["user-1", "user-2"]),
        comments=json.dumps([{"author": "Viewer", "text": "gg"}]),
        is_valid=True,
    )
    match.participants = [
        MatchParticipant(
            nickname="Winner",
            faction="Гондор",
            team=1,
            is_winner=True,
            elo=1420,
            old_rank=12,
            new_rank=10,
        ),
        MatchParticipant(
            nickname="Loser",
            faction="Мордор",
            team=2,
            is_winner=False,
            elo=1370,
            old_rank=10,
            new_rank=12,
        ),
    ]
    db.add_all([viewer, match])
    db.commit()

    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", str(tmp_path))
    replay_path = tmp_path / match.match_id
    replay_path.write_bytes(b"BFME replay")
    match.replay_local_path = str(replay_path)
    match.replay_file_size = replay_path.stat().st_size
    match.replay_download_status = "downloaded"
    db.commit()

    detail = get_match_detail(match.match_id, current_user=viewer, db=db)
    response = asyncio.run(
        download_match_replay(match.match_id, current_user=viewer, db=db)
    )

    assert detail["match_id"] == match.match_id
    assert detail["map_name"] == "Fords of Isen"
    assert detail["arena_id"] == "arena-1"
    assert detail["likes"] == ["user-1", "user-2"]
    assert detail["comments"][0]["text"] == "gg"
    assert detail["participants"][0]["new_rank"] == 10
    assert detail["replay_supported"] is True
    assert detail["replay_archived"] is True
    assert detail["replay_download_url"].endswith("/replay")
    assert Path(response.path) == replay_path


def test_player_rating_uses_latest_snapshot_and_patch_filter(db):
    viewer = User(
        id=1,
        username="Viewer",
        email="viewer@example.test",
        hashed_password="unused",
    )
    db.add(viewer)
    first_match = Match(
        match_id="rating-old",
        winner_player="RatedPlayer",
        winner_faction="Люди",
        loser_player="Opponent",
        loser_faction="Мордор",
        match_date=datetime(2026, 7, 30, 12, 0),
        rating_patch_family="ennorath",
    )
    first_match.participants = [
        MatchParticipant(
            nickname="RatedPlayer",
            faction="Люди",
            team=1,
            is_winner=True,
            elo=1210,
        ),
        MatchParticipant(
            nickname="Opponent",
            faction="Мордор",
            team=2,
            is_winner=False,
            elo=1180,
        ),
    ]
    second_match = Match(
        match_id="rating-new",
        winner_player="OpponentTwo",
        winner_faction="Эльфы",
        loser_player="RatedPlayer",
        loser_faction="Люди",
        match_date=datetime(2026, 7, 31, 12, 0),
        rating_patch_family="ennorath",
    )
    second_match.participants = [
        MatchParticipant(
            nickname="OpponentTwo",
            faction="Эльфы",
            team=1,
            is_winner=True,
            elo=1300,
        ),
        MatchParticipant(
            nickname="RatedPlayer",
            faction="Люди",
            team=2,
            is_winner=False,
            elo=1245,
        ),
    ]
    db.add_all([first_match, second_match])
    db.commit()

    result = asyncio.run(
        get_player_ratings(
            patch="ennorath",
            sort="elo_desc",
            search="Rated",
            min_elo=1200,
            max_elo=1300,
            page=1,
            limit=25,
            current_user=viewer,
            db=db,
        )
    )

    assert result["total_players"] == 1
    assert result["players"][0]["username"] == "RatedPlayer"
    assert result["players"][0]["elo"] == 1245
    assert result["players"][0]["matches"] == 2
    assert result["players"][0]["wins"] == 1


def test_player_rating_includes_claimed_players_without_matches(db):
    viewer = User(
        username="UnratedViewer",
        email="unrated-viewer@example.test",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
    )
    other = User(
        username="NewPlayer",
        email="new-player@example.test",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
    )
    db.add_all([viewer, other])
    db.commit()

    result = asyncio.run(
        get_player_ratings(
            patch="ennorath",
            sort="elo_desc",
            search=None,
            min_elo=None,
            max_elo=None,
            page=1,
            limit=25,
            current_user=viewer,
            db=db,
        )
    )

    assert result["total_players"] == 2
    assert {item["username"] for item in result["players"]} == {"UnratedViewer", "NewPlayer"}
    assert all(item["rated"] is False and item["elo"] is None for item in result["players"])


def test_player_rating_merges_aliases_into_one_person_per_patch(db):
    viewer = User(
        username="AliasViewer",
        email="alias-viewer@example.test",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
    )
    player = User(
        username="CanonicalPlayer",
        email="canonical-player@example.test",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
    )
    identity = ExternalPlayerIdentity(
        user=player,
        source="bfmeladder",
        external_uuid="alias-player-uuid",
        current_nickname="CurrentNick",
    )
    identity.aliases = [ExternalPlayerAlias(nickname="OldNick")]
    db.add_all([viewer, player, identity])

    old_match = Match(
        match_id="alias-old-match",
        winner_player="OldNick",
        winner_faction="Люди",
        loser_player="OpponentA",
        loser_faction="Мордор",
        match_date=datetime(2026, 7, 30, 12, 0),
        rating_patch_family="ennorath",
    )
    old_match.participants = [
        MatchParticipant(nickname="OldNick", team=1, is_winner=True, elo=1200),
        MatchParticipant(nickname="OpponentA", team=2, is_winner=False, elo=1180),
    ]
    current_match = Match(
        match_id="alias-current-match",
        winner_player="OpponentB",
        winner_faction="Эльфы",
        loser_player="CurrentNick",
        loser_faction="Люди",
        match_date=datetime(2026, 7, 31, 12, 0),
        rating_patch_family="ennorath",
    )
    current_match.participants = [
        MatchParticipant(nickname="OpponentB", team=1, is_winner=True, elo=1300),
        MatchParticipant(nickname="CurrentNick", team=2, is_winner=False, elo=1250),
    ]
    db.add_all([old_match, current_match])
    db.commit()

    result = asyncio.run(
        get_player_ratings(
            patch="ennorath",
            sort="elo_desc",
            search="CurrentNick",
            min_elo=None,
            max_elo=None,
            page=1,
            limit=25,
            current_user=viewer,
            db=db,
        )
    )

    assert result["total_players"] == 1
    rated = result["players"][0]
    assert rated["username"] == "CurrentNick"
    assert rated["rating_nickname"] == "CurrentNick"
    assert rated["rating_aliases"] == ["CurrentNick", "OldNick"]
    assert rated["elo"] == 1250
    assert rated["matches"] == 2
    assert rated["wins"] == 1
