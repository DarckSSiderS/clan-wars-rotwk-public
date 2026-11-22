from app.config import settings
from app.models.match import Match
from app.services.ladder_service import BFMELadderService


def replay(*, mode="2 versus 2", patch_name="Patch 2.02 (9.6.5)", patch_id="official-2:9.6.5"):
    return {
        "GameName": "RotWK",
        "GamemodeName": mode,
        "PatchName": patch_name,
        "PatchId": patch_id,
        "IsValid": True,
    }


def test_import_accepts_all_supported_team_modes_and_only_two_patch_families(monkeypatch):
    monkeypatch.setattr(settings, "LADDER_GAME", "RotWK")
    monkeypatch.setattr(
        settings,
        "LADDER_GAMEMODES",
        "1 versus 1,2 versus 2,3 versus 3,4 versus 4",
    )
    monkeypatch.setattr(settings, "LADDER_API_PATCH_FILTER", "")
    service = BFMELadderService()
    for mode in ("1 versus 1", "2 versus 2", "3 versus 3", "4 versus 4"):
        assert service._api_replay_matches_filters(replay(mode=mode)) is True
        assert service._api_replay_matches_filters(replay(
            mode=mode,
            patch_name="Ennorath 1.9.7.7d",
            patch_id="ennorath:1.9.7.7d",
        )) is True

    assert service._api_replay_matches_filters(replay(mode="Free for all")) is False
    assert service._api_replay_matches_filters(replay(
        patch_name="Age of the Ring",
        patch_id="aotr:8.3",
    )) is False


def test_participant_rows_preserve_complete_teams():
    service = BFMELadderService()
    source = replay(mode="2 versus 2") | {
        "Players": [
            {"PlayerAccountUuid": "w1", "FactionName": "Gondor", "Team": 1, "IsWinner": True, "OldRank": 20, "NewRank": 18},
            {"PlayerAccountUuid": "w2", "FactionName": "Rohan", "Team": 1, "IsWinner": True, "OldRank": 30, "NewRank": 25},
            {"PlayerAccountUuid": "l1", "FactionName": "Mordor", "Team": 2, "IsWinner": False, "OldRank": 15, "NewRank": 17},
            {"PlayerAccountUuid": "l2", "FactionName": "Angmar", "Team": 2, "IsWinner": False, "OldRank": 40, "NewRank": 42},
        ]
    }
    rows = service._build_participant_rows(
        source,
        [("WinnerOne", "Gondor", "w1"), ("WinnerTwo", "Rohan", "w2")],
        [("LoserOne", "Mordor", "l1"), ("LoserTwo", "Angmar", "l2")],
        {"participant_ratings": {
            "winnerone": 1200,
            "winnertwo": 1300,
            "loserone": 1250,
            "losertwo": 1100,
        }},
    )

    assert len(rows) == 4
    assert [row["nickname"] for row in rows if row["is_winner"]] == ["WinnerOne", "WinnerTwo"]
    assert [row["nickname"] for row in rows if not row["is_winner"]] == ["LoserOne", "LoserTwo"]
    assert {row["team"] for row in rows} == {1, 2}
    assert {row["elo"] for row in rows} == {1100, 1200, 1250, 1300}


def test_match_import_persists_missing_faction_as_unknown(db):
    saved = BFMELadderService()._save_match_to_db(
        db=db,
        match_id="missing-faction",
        winner_players=[("Winner", "Men", None)],
        loser_players=[("Loser", None, None)],
        match_date="1788307687524",
    )

    match = db.query(Match).filter(Match.match_id == "missing-faction").one()
    assert saved is True
    assert match.winner_faction == "Люди"
    assert match.loser_faction == "Неизвестно"


def test_participant_rows_merge_duplicate_nickname_without_losing_faction():
    service = BFMELadderService()
    source = replay(mode="4 versus 4") | {
        "Players": [
            {"FactionName": "Isengard", "Team": 2, "IsWinner": False},
            {"FactionName": None, "Team": 2, "IsWinner": False},
        ]
    }

    rows = service._build_participant_rows(
        source,
        [("Winner", "Men", None)],
        [("tjololo", "Isengard", None), ("tjololo", None, None)],
        None,
    )

    duplicates = [row for row in rows if row["nickname"] == "tjololo"]
    assert len(duplicates) == 1
    assert duplicates[0]["faction"] == "Изенгард"
