from datetime import datetime, timezone
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from app.models.external_identity import (
    ExternalPlayerAlias,
    ExternalPlayerIdentity,
    canonical_nickname_key,
)
from app.models.match import Match
from app.schemas.user import UserCreate
from app.services.ladder_service import BFMELadderService
from app.services.user_service import UserService


def add_match(db, winner="KnownPlayer", loser="Opponent"):
    db.add(
        Match(
            match_id="identity-test-replay",
            winner_player=winner,
            winner_faction="Люди",
            loser_player=loser,
            loser_faction="Эльфы",
            match_date=datetime(2026, 7, 23, 12, 0),
        )
    )
    db.commit()


def test_external_uuid_survives_nickname_change(db):
    add_match(db)
    service = UserService()

    profile = service.ensure_ladder_profile(
        db,
        "KnownPlayer",
        "player-account-uuid",
    )
    renamed_profile = service.ensure_ladder_profile(
        db,
        "KnownPlayerRenamed",
        "player-account-uuid",
    )

    identity = db.query(ExternalPlayerIdentity).one()
    aliases = {
        item.nickname
        for item in db.query(ExternalPlayerAlias).all()
    }
    assert renamed_profile.id == profile.id
    assert identity.current_nickname == "KnownPlayerRenamed"
    assert identity.current_nickname_key == canonical_nickname_key(
        "KnownPlayerRenamed"
    )
    assert identity.verification_status == "unverified"
    assert aliases == {"KnownPlayer", "KnownPlayerRenamed"}
    assert (
        db.query(ExternalPlayerIdentity)
        .filter(
            ExternalPlayerIdentity.current_nickname_key
            == canonical_nickname_key("knownplayerrenamed")
        )
        .one()
        .id
        == identity.id
    )


def test_canonical_nickname_migration_backfills_existing_identity():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/q3f4g5h6i7j8_add_canonical_arena_nickname_key.py"
    )
    spec = importlib.util.spec_from_file_location(
        "canonical_nickname_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE external_player_identities ("
                "id INTEGER PRIMARY KEY, "
                "current_nickname VARCHAR(120) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO external_player_identities "
                "(id, current_nickname) VALUES (1, :nickname)"
            ),
            {"nickname": "ИгрокStraße"},
        )
        migration.op = Operations(MigrationContext.configure(connection))

        migration.upgrade()

        saved_key = connection.execute(
            text(
                "SELECT current_nickname_key "
                "FROM external_player_identities WHERE id = 1"
            )
        ).scalar_one()
        columns = {
            column["name"]: column
            for column in inspect(connection).get_columns(
                "external_player_identities"
            )
        }
        indexes = {
            index["name"]
            for index in inspect(connection).get_indexes(
                "external_player_identities"
            )
        }
        assert saved_key == canonical_nickname_key("иГРОКSTRASSE")
        assert columns["current_nickname_key"]["nullable"] is False
        assert (
            "ix_external_player_identities_current_nickname_key" in indexes
        )

        migration.downgrade()

        remaining_columns = {
            column["name"]
            for column in inspect(connection).get_columns(
                "external_player_identities"
            )
        }
        assert "current_nickname_key" not in remaining_columns


def test_replay_import_persists_player_uuids_and_identities(db):
    saved = BFMELadderService()._save_match_to_db(
        db=db,
        match_id="uuid-import-replay",
        winner_players=[("WinnerName", "Men", "winner-uuid")],
        loser_players=[("LoserName", "Elves", "loser-uuid")],
        match_date="1753272000000",
        api_metadata={
            "Duration": "00:10:00",
            "GameName": "RotWK",
            "GamemodeName": "1 versus 1",
            "EloDelta": 14,
            "IsValid": True,
        },
    )

    match = db.query(Match).filter(Match.match_id == "uuid-import-replay").one()
    identities = {
        identity.external_uuid: identity.current_nickname
        for identity in db.query(ExternalPlayerIdentity).all()
    }
    assert saved is True
    assert match.winner_player_uuid == "winner-uuid"
    assert match.loser_player_uuid == "loser-uuid"
    assert match.duration == "00:10:00"
    assert match.gamemode_name == "1 versus 1"
    assert match.elo_delta == 14
    assert match.is_valid is True
    assert identities == {
        "winner-uuid": "WinnerName",
        "loser-uuid": "LoserName",
    }


def test_replay_timestamp_is_saved_as_utc():
    timestamp_ms = "1753272000000"

    parsed = BFMELadderService()._parse_match_date(timestamp_ms)

    assert parsed == datetime.fromtimestamp(
        int(timestamp_ms) / 1000,
        tz=timezone.utc,
    )


def test_known_match_lookup_is_limited_to_current_replay_ids(db):
    db.add_all(
        [
            Match(
                match_id="current-replay",
                winner_player="Winner",
                winner_faction="Люди",
                loser_player="Loser",
                loser_faction="Эльфы",
                match_date=datetime(2026, 7, 23, 12, 0),
            ),
            Match(
                match_id="old-replay-outside-window",
                winner_player="OldWinner",
                winner_faction="Люди",
                loser_player="OldLoser",
                loser_faction="Эльфы",
                match_date=datetime(2026, 7, 22, 12, 0),
            ),
        ]
    )
    db.commit()

    known = BFMELadderService()._known_matches_for_replay_ids(
        db,
        [
            ("current-replay", {}),
            ("missing-replay", {}),
        ],
    )

    assert set(known) == {"current-replay"}


def test_known_replay_uuid_backfill_uses_api_player_result(db):
    add_match(db)
    match = db.query(Match).filter(Match.match_id == "identity-test-replay").one()

    updated = BFMELadderService()._backfill_known_match_identity(
        db,
        match,
        {
            "Players": [
                {
                    "PlayerAccountUuid": "known-winner-uuid",
                    "IsWinner": True,
                    "IsObserver": False,
                },
                {
                    "PlayerAccountUuid": "known-loser-uuid",
                    "IsWinner": False,
                    "IsObserver": False,
                },
            ]
        },
    )

    assert updated is True
    assert match.winner_player_uuid == "known-winner-uuid"
    assert match.loser_player_uuid == "known-loser-uuid"
    assert db.query(ExternalPlayerIdentity).count() == 2


def test_claimed_ladder_profile_keeps_progress_and_requires_verification(db):
    add_match(db)
    service = UserService()
    profile = service.ensure_ladder_profile(
        db,
        "KnownPlayer",
        "player-account-uuid",
    )
    profile.level = 7
    profile.experience = 345
    db.commit()

    claimed = service.create_user(
        db,
        UserCreate(
            username="KnownPlayer",
            email="known@example.com",
            password="strong-test-password",
            claim_existing_profile=True,
        ),
    )

    assert claimed.id == profile.id
    assert claimed.level == 7
    assert claimed.experience == 345
    assert claimed.is_claimed is True
    assert claimed.external_identity_status == "pending"
