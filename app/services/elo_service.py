import asyncio
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Optional
from time import monotonic
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup

PATCH_202 = "patch_202"
PATCH_ENNORATH = "ennorath"
PATCH_ALL = "all"
SUPPORTED_CLAN_PATCHES = {PATCH_202, PATCH_ENNORATH, PATCH_ALL}


def get_patch_family(patch_name: Optional[str], patch_id: Optional[str] = None) -> Optional[str]:
    patch_text = f"{patch_name or ''} {patch_id or ''}".lower()
    if "ennorath" in patch_text:
        return PATCH_ENNORATH
    if "2.02" in patch_text or "official-2:" in patch_text:
        return PATCH_202
    return None


def get_patch_label(patch_family: Optional[str]) -> str:
    return {
        PATCH_202: "Patch 2.02",
        PATCH_ENNORATH: "Ennorath",
        PATCH_ALL: "Все патчи",
    }.get(patch_family, "Неизвестный патч")


def expected_score(
    player_rating: float,
    opponent_rating: float,
    rules: Mapping[str, int | float],
) -> float:
    divisor = float(rules["ELO_EXPECTED_SCORE_DIVISOR"])
    return 1 / (1 + 10 ** ((opponent_rating - player_rating) / divisor))


def winner_territory_points(
    win_probability: float,
    rules: Mapping[str, int | float],
) -> int:
    raw_points = round(
        float(rules["WAR_ELO_BASE_POINTS"])
        * (float(rules["WAR_ELO_EXPECTED_WEIGHT"]) - win_probability)
    )
    return min(
        int(rules["WAR_ELO_MAX_POINTS"]),
        max(int(rules["WAR_ELO_MIN_POINTS"]), raw_points),
    )


def draw_territory_points(
    expected_probability: float,
    rules: Mapping[str, int | float],
) -> int:
    raw_points = round(
        float(rules["WAR_ELO_BASE_POINTS"])
        * (float(rules["WAR_ELO_EXPECTED_WEIGHT"]) - expected_probability)
        / float(rules["WAR_ELO_DRAW_DIVISOR"])
    )
    return min(
        int(rules["WAR_ELO_MAX_DRAW_POINTS"]),
        max(int(rules["WAR_ELO_MIN_DRAW_POINTS"]), raw_points),
    )


def k_factor(rated_matches: int, rules: Mapping[str, int | float]) -> int:
    threshold = int(rules["ELO_PROVISIONAL_MATCHES"])
    key = "ELO_PROVISIONAL_K" if rated_matches < threshold else "ELO_REGULAR_K"
    return int(rules[key])


class BfmeProfileRatingService:
    """Reads one current 1v1 Elo snapshot from a public BFME Arena profile."""

    profile_base_url = "https://bfmeladder.com/u"

    def __init__(self):
        self._ladder_cache = {}
        self._ladder_locks = {}

    async def _fetch_ladder_ratings(self, session, patch_family):
        from app.config import settings

        lock = self._ladder_locks.setdefault(patch_family, asyncio.Lock())
        async with lock:
            cached = self._ladder_cache.get(patch_family)
            if cached and monotonic() - cached[0] < 300:
                return cached[1]
            arena = (settings.LADDER_PATCH_202_ARENA_ID if patch_family == PATCH_202
                     else settings.LADDER_ENNORATH_ARENA_ID)
            try:
                async with session.get(
                    'https://bfmeladder.com/ladders',
                    params={'arena': arena, 'gamemode': '1 versus 1'},
                    headers={'Accept': 'text/html'},
                ) as response:
                    if response.status != 200:
                        return []
                    soup = BeautifulSoup(await response.text(), 'html.parser')
            except Exception:
                return []
            heading = soup.find('h1')
            title = heading.get_text(' ', strip=True) if heading else ''
            if 'rotwk' not in title.casefold() or get_patch_family(title) != patch_family:
                return []
            rows = []
            for row in soup.select('tr'):
                name = row.select_one('.ladderUsername a')
                score = row.select_one('.col-score')
                avatar = row.select_one('.miniProfilePicture')
                if not name or not score:
                    continue
                digits = score.get_text(strip=True).replace(',', '').replace(' ', '')
                if not digits.isdigit():
                    continue
                avatar_path = urlparse(avatar.get('src', '')).path if avatar else ''
                uuid_match = re.search(r'/avatars/([0-9a-f-]{36})\.', avatar_path, re.I)
                rows.append((name.get_text(' ', strip=True).casefold(),
                             uuid_match.group(1).casefold() if uuid_match else None,
                             int(digits)))
            self._ladder_cache[patch_family] = (monotonic(), rows)
            return rows

    async def fetch_elo(
        self,
        session,
        nickname: str,
        patch_family: str,
        player_uuid: Optional[str] = None,
    ) -> Optional[int]:
        if patch_family not in {PATCH_202, PATCH_ENNORATH}:
            return None

        # UUID matching survives renamed players and broken whitespace profile URLs.
        if player_uuid:
            rows = await self._fetch_ladder_ratings(session, patch_family)
            values = [rating for _, uuid, rating in rows if uuid == player_uuid.casefold()]
            if not values:
                # Arena uses a generic avatar for some players, so their rows lack a UUID.
                values = [rating for name, uuid, rating in rows
                          if uuid is None and name == nickname.strip().casefold()]
            return values[0] if len(values) == 1 else None

        rating = await self._fetch_profile_elo(session, nickname, patch_family)
        if rating is not None:
            return rating
        rows = await self._fetch_ladder_ratings(session, patch_family)
        values = [rating for name, _, rating in rows if name == nickname.strip().casefold()]
        return values[0] if len(values) == 1 else None

    async def _fetch_profile_elo(self, session, nickname, patch_family):

        url = f"{self.profile_base_url}/{quote(nickname, safe='')}"
        try:
            async with session.get(url, headers={"Accept": "text/html"}) as response:
                if response.status != 200:
                    return None
                html = await response.text()
        except Exception:
            return None

        soup = BeautifulSoup(html, "html.parser")
        patch_marker = "patch 2.02" if patch_family == PATCH_202 else "ennorath"
        for elo_text in soup.find_all(
            string=lambda value: value and value.strip().upper() == "ELO"
        ):
            elo_element = elo_text.parent
            rating_row = elo_element.parent if elo_element else None
            card = rating_row.parent if rating_row else None
            if not card:
                continue
            card_text = " ".join(card.stripped_strings).lower()
            if (
                "rotwk" not in card_text
                or patch_marker not in card_text
                or "1 versus 1" not in card_text
            ):
                continue
            rating_element = rating_row.find("div", recursive=False)
            if not rating_element:
                continue
            rating_match = re.search(r"\d+", rating_element.get_text(strip=True))
            if rating_match:
                return int(rating_match.group(0))
        return None


def rating_capture_timestamp() -> datetime:
    return datetime.now(timezone.utc)


def is_unverified_rating(match, player_uuid, nickname) -> bool:
    markers = (match.source_payload or {}).get('rating_unverified_players', [])
    return any(
        (player_uuid and str(player_uuid).casefold() == str(entry.get('uuid', '')).casefold())
        or (not player_uuid and str(nickname).strip().casefold() == str(entry.get('nickname', '')).strip().casefold())
        for entry in markers
    )
