import pytest
from datetime import datetime

from app.config import Settings, settings
from app.models.match import Match, MatchParticipant
from app.services.ladder_service import BFMELadderService, ReplaySourceError


COMPLETED_REPLAY_HTML = """
<html><body>
  <div class="replay-card" id="replay-123.BfME2Replay">
    <div class="teams-row">
      <div class="team-col team-left">
        <div class="team-title">Winners</div>
        <div class="player-row player-winner">
          <div class="player-info">
            <div class="player-name">
              <a href="/u/WinnerOne">WinnerOne</a>
              <img class="armyIcon" src="https://cdn.example/army-icons/elves.png">
            </div>
            <div class="player-rank">197th ➔ 174th</div>
          </div>
        </div>
      </div>
      <div class="team-col team-right">
        <div class="team-title">Losers</div>
        <div class="player-row player-loser">
          <div class="player-info">
            <div class="player-name">
              <img class="armyIcon" src="https://cdn.example/army-icons/dwarves.png">
              <a href="/u/LoserOne">LoserOne</a>
            </div>
            <div class="player-rank">unranked ➔ 358th</div>
          </div>
        </div>
      </div>
    </div>
    <div class="map-block">
      <img class="mapImage" src="https://cdn.example/maps/stockbrook.png">
      <div class="map-name">Fords of Stockbrook</div>
    </div>
    <div class="meta-row"><span class="meta-label">Game</span><span class="meta-value">RotWK</span></div>
    <div class="meta-row"><span class="meta-label">Patch</span><span class="meta-value">Patch 2.02 (9.7.7)</span></div>
    <div class="meta-row"><span class="meta-label">Gamemode</span><span class="meta-value">1 versus 1</span></div>
    <div class="meta-row"><span class="meta-label">Duration</span><span class="meta-value">00:04:10</span></div>
    <div class="meta-row"><span class="meta-label">Date</span><span class="meta-value unixDate">1788204198589</span></div>
    <div class="meta-row"><span class="meta-label">ELO +/-</span><span class="meta-value">10</span></div>
    <div class="meta-row"><span class="meta-label">Downloads</span><span class="meta-value">2</span></div>
    <div class="meta-row"><span class="meta-label">Replay</span><span class="meta-value"><a class="replay-dl" href="https://bfmeladder.com/api/replays/download?replayId=replay-123.BfME2Replay">Download</a></span></div>
  </div>
  <div class="replay-card" id="live-replay">
    <div class="team-title">Team 1</div><div class="team-title">Team 2</div>
    <div class="meta-row"><span class="meta-label">Duration</span><span class="meta-value">-</span></div>
  </div>
</body></html>
"""


class _HtmlResponse:
    status = 200

    def __init__(self, html):
        self.html = html

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        return self.html


class _HtmlSession:
    def __init__(self, html):
        self.html = html
        self.requests = []

    def get(self, url, *, params=None, headers=None):
        self.requests.append((url, params, headers))
        return _HtmlResponse(self.html)


class _PagedHtmlSession:
    def __init__(self, pages):
        self.pages = pages
        self.requests = []

    def get(self, url, *, params=None, headers=None):
        self.requests.append((url, params, headers))
        return _HtmlResponse(self.pages[params["page"]])


@pytest.mark.parametrize('label,kind', [
    ('+10 ELO', 'ladder'), ('+10 CW', 'clan_war'), ('+10', 'unspecified'),
])
def test_html_preserves_rating_evidence_without_treating_tooltip_as_rank(label, kind):
    tooltip = (f'<span class="rx"><button class="rx-btn">{label}</button>'
               '<span class="rx-pop"><ul><li>Rating before: 1152</li>'
               '<li>Side average: 1152 against 1203.</li>'
               '<li>Rating after: 1162</li></ul></span></span>')
    html = COMPLETED_REPLAY_HTML.replace('197th ➔ 174th', f'197th ➔ 174th · {tooltip}')
    player = BFMELadderService()._parse_html_replays(html, scan_limit=50)[0][1]['Players'][0]
    assert (player['OldRank'], player['NewRank']) == (197, 174)
    assert player['ArenaRatingEvidence'] == {
        'before': 1152, 'after': 1162, 'kind': kind,
        'source': 'replay_html_tooltip', 'time_semantics_verified': False,
    }
    assert player['PlayerAccountUuid'] is None
    assert 'HistoricalElo' not in player


@pytest.mark.parametrize('details', [
    '<li>Rating before: -1</li><li>Rating after: 1162</li>',
    '<li>Rating before: 1152</li><li>Rating before: 1200</li><li>Rating after: 1162</li>',
    '<li>Rating before: unknown</li><li>Rating after: 1162</li>',
])
def test_html_does_not_invent_elo_for_ambiguous_rating_evidence(details):
    html = COMPLETED_REPLAY_HTML.replace('197th ➔ 174th',
        f'197th ➔ 174th <span class="rx"><button class="rx-btn">+10 ELO</button>'
        f'<span class="rx-pop"><ul>{details}</ul></span></span>')
    player = BFMELadderService()._parse_html_replays(html, scan_limit=50)[0][1]['Players'][0]
    assert player.get('ArenaRatingEvidence') is None
    assert (player['OldRank'], player['NewRank']) == (197, 174)


def test_html_single_rank_ignores_tooltip_numbers():
    html = COMPLETED_REPLAY_HTML.replace('197th ➔ 174th',
        '3rd · <span class="rx"><button class="rx-btn">+10 ELO</button>'
        '<span class="rx-pop"><ul><li>Rating before: 1152</li>'
        '<li>Rating after: 1162</li></ul></span></span>')
    player = BFMELadderService()._parse_html_replays(html, scan_limit=50)[0][1]['Players'][0]
    assert (player['OldRank'], player['NewRank']) == (3, 3)


def test_rating_evidence_survives_metadata_storage_without_becoming_historical_elo():
    html = COMPLETED_REPLAY_HTML.replace('197th ➔ 174th',
        '197th ➔ 174th <span class="rx"><button class="rx-btn">+10 ELO</button>'
        '<span class="rx-pop"><ul><li>Rating before: 1152</li>'
        '<li>Rating after: 1162</li></ul></span></span>')
    replay = BFMELadderService()._parse_html_replays(html, scan_limit=50)[0][1]
    match = Match(winner_elo=800, loser_elo=900, rating_source='bfmeladder_current')
    BFMELadderService._apply_api_replay_metadata(match, replay)
    assert match.source_payload['Players'][0]['ArenaRatingEvidence']['before'] == 1152
    assert match.source_payload['Players'][0]['ArenaRatingEvidence']['time_semantics_verified'] is False
    assert (match.winner_elo, match.loser_elo, match.rating_source) == (800, 900, 'bfmeladder_current')


def test_ladder_gamemodes_normalize_multiline_environment_value():
    configured = Settings(
        LADDER_GAMEMODES=(
            "1\nversus\n1,2\nversus\n2,3\nversus\n3,4\nversus\n4"
        )
    )

    assert configured.LADDER_GAMEMODES == (
        "1 versus 1,2 versus 2,3 versus 3,4 versus 4"
    )


def test_html_replay_parser_preserves_ranked_match_metadata(monkeypatch):
    monkeypatch.setattr(
        settings,
        "LADDER_GAMEMODES",
        "1 versus 1,2 versus 2,3 versus 3,4 versus 4",
    )
    service = BFMELadderService()

    result = service._parse_html_replays(COMPLETED_REPLAY_HTML, scan_limit=50)

    assert len(result) == 1
    replay_id, replay = result[0]
    assert replay_id == "replay-123.BfME2Replay"
    assert replay["GameName"] == "RotWK"
    assert replay["PatchName"] == "Patch 2.02 (9.7.7)"
    assert replay["GamemodeName"] == "1 versus 1"
    assert replay["MapName"] == "Fords of Stockbrook"
    assert replay["EloDelta"] == 10
    assert replay["Downloads"] == 2
    assert replay["ReplayDownloadUrl"].endswith(replay_id)
    assert replay["Players"] == [
        {
            "PlayerAccountUuid": None,
            "DisplayName": "WinnerOne",
            "FactionName": "elves",
            "Team": 1,
            "IsWinner": True,
            "IsObserver": False,
            "OldRank": 197,
            "NewRank": 174,
        },
        {
            "PlayerAccountUuid": None,
            "DisplayName": "LoserOne",
            "FactionName": "dwarves",
            "Team": 2,
            "IsWinner": False,
            "IsObserver": False,
            "OldRank": None,
            "NewRank": 358,
        },
    ]


def test_html_replay_parser_maps_ennorath_uuid_faction_icons(monkeypatch):
    monkeypatch.setattr(settings, "LADDER_GAMEMODES", "1 versus 1")
    html = COMPLETED_REPLAY_HTML.replace(
        "army-icons/elves.png",
        "factions/73a97e8e-bd4c-450c-87d9-4596e7b68e59.png",
    ).replace(
        "army-icons/dwarves.png",
        "factions/806c09f6-3abf-479b-b97a-b856d80b0e02.png",
    )

    _, replay = BFMELadderService()._parse_html_replays(html, scan_limit=50)[0]

    assert replay["Players"][0]["FactionName"] == "Мглистые Горы"
    assert replay["Players"][1]["FactionName"] == "Изенгард"


def test_known_match_sync_repairs_top_level_and_participant_factions(db):
    service = BFMELadderService()
    html = COMPLETED_REPLAY_HTML.replace(
        "army-icons/elves.png",
        "factions/73a97e8e-bd4c-450c-87d9-4596e7b68e59.png",
    ).replace(
        "army-icons/dwarves.png",
        "factions/806c09f6-3abf-479b-b97a-b856d80b0e02.png",
    )
    _, replay = service._parse_html_replays(html, scan_limit=50)[0]
    match = Match(
        match_id="replay-123.BfME2Replay",
        winner_player="WinnerOne",
        winner_faction="73a97e8e bd4c 450c 87d9 4596e7b68e59",
        loser_player="LoserOne",
        loser_faction="806c09f6 3abf 479b b97a b856d80b0e02",
        match_date=datetime(2026, 8, 31),
        participants=[
            MatchParticipant(
                nickname="WinnerOne",
                faction="73a97e8e bd4c 450c 87d9 4596e7b68e59",
                team=1,
                is_winner=True,
            ),
            MatchParticipant(
                nickname="LoserOne",
                faction="806c09f6 3abf 479b b97a b856d80b0e02",
                team=2,
                is_winner=False,
            ),
        ],
    )
    db.add(match)
    db.commit()

    changed = service._backfill_known_match_identity(db, match, replay)

    assert changed is True
    assert match.winner_faction == "Мглистые Горы"
    assert match.loser_faction == "Изенгард"
    assert [participant.faction for participant in match.participants] == [
        "Мглистые Горы",
        "Изенгард",
    ]


@pytest.mark.asyncio
async def test_html_source_is_used_without_public_api_token(db, monkeypatch):
    monkeypatch.setattr(settings, "LADDER_PUBLIC_API_ENABLED", False)
    monkeypatch.setattr(settings, "LADDER_PUBLIC_API_TOKEN", "")
    session = _HtmlSession(COMPLETED_REPLAY_HTML)
    service = BFMELadderService()

    result = await service._load_api_replays(session, db, scan_limit=50)

    assert len(result) == 1
    assert service.last_source == "bfme_arena_html"
    assert service.last_scanned_count == 1
    assert session.requests[0][0] == settings.LADDER_BASE
    assert session.requests[0][1] == {"game": "RotWK", "q": ""}


@pytest.mark.asyncio
async def test_html_source_rejects_successful_but_invalid_payload(db, monkeypatch):
    monkeypatch.setattr(settings, "LADDER_PUBLIC_API_ENABLED", False)
    monkeypatch.setattr(settings, "LADDER_PUBLIC_API_TOKEN", "")
    service = BFMELadderService()

    with pytest.raises(ReplaySourceError, match="no replay cards"):
        await service._load_api_replays(
            _HtmlSession("method_not_found"),
            db,
            scan_limit=50,
        )


@pytest.mark.asyncio
async def test_html_source_accepts_valid_empty_search_page(db, monkeypatch):
    monkeypatch.setattr(settings, "LADDER_PUBLIC_API_ENABLED", False)
    monkeypatch.setattr(settings, "LADDER_PUBLIC_API_TOKEN", "")
    service = BFMELadderService()

    result = await service._load_api_replays(
        _HtmlSession('<html><div id="replays">No replays found</div></html>'),
        db,
        scan_limit=50,
        player_query="missing-player",
    )

    assert result == []
    assert service.last_source == "bfme_arena_html"
    assert service.last_scanned_count == 0


@pytest.mark.asyncio
async def test_player_history_follows_every_arena_archive_page(db, monkeypatch):
    monkeypatch.setattr(settings, "LADDER_PUBLIC_API_ENABLED", False)
    first_page = COMPLETED_REPLAY_HTML.replace(
        "</body>",
        "<div class='replay-pagination-controls'>"
        "<a class='replay-page-btn' href='?page=2'>Next</a></div></body>",
    )
    second_page = (
        COMPLETED_REPLAY_HTML
        .replace("replay-123.BfME2Replay", "replay-older.BfME2Replay")
        .replace("1788204198589", "1688204198589")
    )
    session = _PagedHtmlSession({1: first_page, 2: second_page})
    service = BFMELadderService()

    result = await service._load_html_replays(
        session,
        scan_limit=None,
        player_query="ArenaPlayer",
        paginate_all=True,
    )

    assert [replay_id for replay_id, _ in result] == [
        "replay-123.BfME2Replay",
        "replay-older.BfME2Replay",
    ]
    assert [request[1]["page"] for request in session.requests] == [1, 2]
    assert all(
        request[1]["q"] == "ArenaPlayer" for request in session.requests
    )
    assert service.last_scanned_count == 2


@pytest.mark.asyncio
async def test_pagination_does_not_treat_page_twenty_as_page_two():
    page = COMPLETED_REPLAY_HTML.replace('</body>',
        "<div class='replay-pagination-controls'>"
        "<a class='replay-page-btn' href='?page=20'>20</a></div></body>")
    session = _PagedHtmlSession({1: page, 2: '<div id="replays">No replays found</div>'})
    with pytest.raises(ReplaySourceError, match='pagination'):
        await BFMELadderService()._load_html_replays(session, None, paginate_all=True)
    assert [r[1]['page'] for r in session.requests] == [1]


@pytest.mark.asyncio
async def test_repeated_archive_page_cannot_certify_complete_scan(monkeypatch):
    monkeypatch.setattr(settings, 'ARENA_BACKFILL_MAX_PAGES', 3)
    page = COMPLETED_REPLAY_HTML.replace('</body>',
        "<div class='replay-pagination-controls'>"
        "<a class='replay-page-btn' href='?page=2'>2</a></div></body>")
    session = _PagedHtmlSession({1: page, 2: page})
    with pytest.raises(ReplaySourceError, match='repeated'):
        await BFMELadderService()._load_html_replays(session, None, paginate_all=True)


@pytest.mark.asyncio
async def test_old_pinned_replay_does_not_hide_remaining_window_pages():
    recent = COMPLETED_REPLAY_HTML.replace('1788204198589', '1800000000000')
    pinned = COMPLETED_REPLAY_HTML.replace('replay-123.BfME2Replay', 'pinned').replace(
        '1788204198589', '1600000000000')
    first = recent.replace('</body>', pinned +
        "<div class='replay-pagination-controls'>"
        "<a class='replay-page-btn' href='?page=2'>Next</a></div></body>")
    second = COMPLETED_REPLAY_HTML.replace('replay-123.BfME2Replay', 'missed-match')
    session = _PagedHtmlSession({1: first, 2: second})
    result = await BFMELadderService()._load_html_replays(session, None, paginate_all=True,
        start_override_ms=1700000000000)
    assert {key for key, _ in result} == {'replay-123.BfME2Replay', 'missed-match'}
    assert [request[1]['page'] for request in session.requests] == [1, 2]


@pytest.mark.asyncio
async def test_player_history_forces_html_search_and_preserves_worker_cursor(
    db,
    monkeypatch,
):
    monkeypatch.setattr(settings, "LADDER_PUBLIC_API_ENABLED", True)
    monkeypatch.setattr(settings, "LADDER_PUBLIC_API_TOKEN", "configured-token")
    service = BFMELadderService()
    captured = {}

    async def capture_import(session, new_limit, **kwargs):
        captured.update(kwargs)
        return 4

    monkeypatch.setattr(service, "fetch_and_save_matches_from_api", capture_import)

    imported = await service.fetch_and_save_player_history(db, "  ArenaPlayer  ")

    assert imported == 4
    assert captured == {
        "advance_cursor": False,
        "player_query": "ArenaPlayer",
        "full_player_history": True,
    }


@pytest.mark.asyncio
async def test_visible_html_players_do_not_require_detail_request():
    service = BFMELadderService()
    _, replay = service._parse_html_replays(COMPLETED_REPLAY_HTML, scan_limit=50)[0]

    winners, losers = await service._fetch_replay_players(
        _HtmlSession(""),
        "replay-123.BfME2Replay",
        replay,
    )

    assert winners == [("WinnerOne", "elves", None)]
    assert losers == [("LoserOne", "dwarves", None)]


@pytest.mark.asyncio
async def test_sync_propagates_source_failure_to_worker_layer(db, monkeypatch):
    service = BFMELadderService()

    async def fail_source(*args, **kwargs):
        raise ReplaySourceError("archive contract changed")

    monkeypatch.setattr(service, "_load_api_replays", fail_source)

    with pytest.raises(ReplaySourceError, match="archive contract changed"):
        await service.fetch_and_save_matches_from_api(db, new_limit=1)
