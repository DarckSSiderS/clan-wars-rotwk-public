from datetime import datetime
import hashlib

import pytest

from app.models.match import Match
from app.services.ladder_service import BFMELadderService
from app.services.replay_storage_service import ReplayStorageService


class FakeContent:
    def __init__(self, chunks):
        self.chunks = chunks

    async def iter_chunked(self, _size):
        for chunk in self.chunks:
            yield chunk


class FakeResponse:
    def __init__(self, chunks, status=200):
        self.status = status
        self.content = FakeContent(chunks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class FakeSession:
    def __init__(self, chunks):
        self.chunks = chunks
        self.urls = []

    def get(self, url, **_kwargs):
        self.urls.append(url)
        return FakeResponse(self.chunks)


def make_match(match_id, patch_name):
    return Match(
        match_id=match_id,
        winner_player="Winner",
        winner_faction="Men",
        loser_player="Loser",
        loser_faction="Mordor",
        match_date=datetime(2026, 7, 28, 18, 0),
        patch_name=patch_name,
        patch_version=patch_name,
    )


@pytest.mark.asyncio
async def test_supported_replay_is_saved_with_hash_and_path(db, tmp_path):
    payload = [b"BFME replay ", b"payload"]
    session = FakeSession(payload)
    match = make_match("replay-202", "Patch 2.02 (9.7.7)")
    db.add(match)
    db.commit()

    saved = await ReplayStorageService(tmp_path).download_match(db, match, session)

    expected_file = tmp_path / "replay-202.BfME2Replay"
    assert saved is True
    assert expected_file.read_bytes() == b"".join(payload)
    assert match.replay_download_status == "downloaded"
    assert match.replay_file_size == len(b"".join(payload))
    assert match.replay_sha256 == hashlib.sha256(b"".join(payload)).hexdigest()
    assert match.replay_local_path == str(expected_file.resolve())
    assert session.urls == [
        "https://bfmeladder.com/api/replays/download?replayId=replay-202"
    ]


@pytest.mark.asyncio
async def test_unsupported_mod_is_never_downloaded(db, tmp_path):
    session = FakeSession([b"must not be downloaded"])
    match = make_match("replay-other", "Edain Unchained")
    db.add(match)
    db.commit()

    saved = await ReplayStorageService(tmp_path).download_match(db, match, session)

    assert saved is False
    assert session.urls == []
    assert list(tmp_path.iterdir()) == []
    assert match.replay_download_status is None


def test_api_payload_and_player_ranks_are_preserved():
    match = make_match("replay-details", "Patch 2.02")
    replay = {
        "ReplayId": "replay-details",
        "PatchName": "Patch 2.02",
        "Likes": [{"Player": "Tester"}],
        "Comments": [{"Text": "gg"}],
        "Players": [
            {
                "PlayerAccountUuid": "winner-uuid",
                "FactionIndex": 1,
                "IsWinner": True,
                "OldRank": 12,
                "NewRank": 10,
            },
            {
                "PlayerAccountUuid": "loser-uuid",
                "FactionIndex": 3,
                "IsWinner": False,
                "OldRank": 8,
                "NewRank": 9,
            },
        ],
    }

    changed = BFMELadderService._apply_api_replay_metadata(match, replay)

    assert changed is True
    assert match.source_payload == replay
    assert match.winner_faction_index == 1
    assert match.winner_old_rank == 12
    assert match.winner_new_rank == 10
    assert match.loser_faction_index == 3
    assert match.loser_old_rank == 8
    assert match.loser_new_rank == 9
