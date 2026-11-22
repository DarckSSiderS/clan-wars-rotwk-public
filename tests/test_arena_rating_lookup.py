import asyncio
from types import SimpleNamespace

import pytest

from app.services.elo_service import BfmeProfileRatingService, is_unverified_rating
from app.services.ladder_service import BFMELadderService


UUID = '94faacf9-b789-4068-9e9d-f421b9e670c2'
LADDER = f'''<h1>Ladders: RotWK Ennorath</h1>
<table><tr><td class="col-name"><img class="miniProfilePicture" src="https://arena-files.bfmeladder.com/avatars/{UUID}.png">
<span class="ladderUsername"><a href="/u/Amelie%20">Amelie </a></span></td>
<td class="col-wins">167</td><td class="col-score">1227</td></tr></table>'''


class Response:
    def __init__(self, html, status=200):
        self.html, self.status = html, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def text(self):
        return self.html


class Session:
    def __init__(self, ladder=LADDER):
        self.ladder = ladder
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return Response(self.ladder) if '/ladders' in url else Response('', 404)


@pytest.mark.asyncio
async def test_uuid_rating_survives_broken_profile_and_changed_name():
    session = Session()
    assert await BfmeProfileRatingService().fetch_elo(
        session, 'Old nickname', 'ennorath', player_uuid=UUID
    ) == 1227


@pytest.mark.asyncio
async def test_failed_profile_uses_exact_unambiguous_ladder_name():
    assert await BfmeProfileRatingService().fetch_elo(Session(), 'Amelie', 'ennorath') == 1227


@pytest.mark.asyncio
async def test_uuid_mismatch_never_uses_recycled_nickname():
    assert await BfmeProfileRatingService().fetch_elo(
        Session(), 'Amelie', 'ennorath', player_uuid='different-player'
    ) is None


@pytest.mark.asyncio
async def test_generic_avatar_uses_unique_current_name_without_false_uuid_match():
    session = Session(LADDER.replace(UUID + '.png', 'default.png'))
    assert await BfmeProfileRatingService().fetch_elo(
        session, 'Amelie', 'ennorath', player_uuid=UUID
    ) == 1227


@pytest.mark.asyncio
async def test_parallel_lookups_share_one_ladder_request_and_force_1v1():
    service, session = BfmeProfileRatingService(), Session()
    assert await asyncio.gather(*[
        service.fetch_elo(session, 'Amelie', 'ennorath', player_uuid=UUID)
        for _ in range(3)
    ]) == [1227] * 3
    assert len(session.requests) == 1
    assert session.requests[0][1]['params']['gamemode'] == '1 versus 1'


@pytest.mark.asyncio
async def test_wrong_patch_table_is_not_used():
    session = Session(LADDER.replace('RotWK Ennorath', 'RotWK Patch 2.02'))
    assert await BfmeProfileRatingService().fetch_elo(
        session, 'Amelie', 'ennorath', player_uuid=UUID
    ) is None


@pytest.mark.asyncio
async def test_missing_rating_is_not_persisted_as_starting_elo():
    service = BFMELadderService()
    result = await service._capture_team_ratings(
        Session('<h1>Ladders: RotWK Ennorath</h1>'),
        {'PatchName': 'Ennorath'},
        [('Amelie', None, UUID)], [('Opponent', None, 'other')], {}, 1000,
    )
    assert result['winner_elo'] is None
    assert result['loser_elo'] is None
    assert result['participant_ratings']['amelie'] is None
    assert result['source'] == 'bfmeladder_rating_incomplete'


def test_historical_warning_follows_uuid_without_marking_other_player():
    match = SimpleNamespace(source_payload={'rating_unverified_players': [{'uuid': UUID, 'nickname': 'Amelie'}]})
    assert is_unverified_rating(match, UUID, 'Renamed player')
    assert is_unverified_rating(match, None, 'Amelie')
    assert not is_unverified_rating(match, 'another-uuid', 'Amelie')


def test_replay_metadata_refresh_preserves_historical_rating_warning():
    from app.models.match import Match

    marker = [{'uuid': UUID, 'nickname': 'Amelie'}]
    match = Match(source_payload={'rating_unverified_players': marker})
    BFMELadderService._apply_api_replay_metadata(match, {'PatchName': 'Ennorath'})
    assert match.source_payload['rating_unverified_players'] == marker


def test_match_details_mark_legacy_elo_without_changing_stored_value():
    from datetime import datetime
    from app.api.v1.statistics import _match_detail_payload
    from app.models.match import Match, MatchParticipant

    match = Match(match_id='legacy', winner_player='Amelie', loser_player='Other',
                  winner_faction='Men', loser_faction='Elves', match_date=datetime(2026, 9, 30),
                  source_payload={'rating_unverified_players': [{'uuid': UUID, 'nickname': 'Amelie'}]})
    match.participants = [MatchParticipant(nickname='Amelie', player_uuid=UUID, elo=1000)]
    payload = _match_detail_payload(match)
    assert payload['rating_warning'] is True
    assert payload['participants'][0]['elo_is_verified'] is False
    assert match.participants[0].elo == 1000
