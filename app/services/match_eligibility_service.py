from collections.abc import Mapping
from typing import Optional

from app.models.match import Match
from app.config import settings
from app.core.time import as_utc


RANKED_MODE_TEAM_SIZES = {
    "1 versus 1": 1,
    "1 vs 1": 1,
    "1v1": 1,
    "2 versus 2": 2,
    "2 vs 2": 2,
    "2v2": 2,
    "3 versus 3": 3,
    "3 vs 3": 3,
    "3v3": 3,
    "4 versus 4": 4,
    "4 vs 4": 4,
    "4v4": 4,
}


def parse_match_duration_seconds(duration: Optional[str]) -> Optional[int]:
    if not duration:
        return None
    try:
        parts = [int(part) for part in str(duration).strip().split(":")]
    except (TypeError, ValueError):
        return None
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return hours * 3600 + minutes * 60 + seconds
    if len(parts) == 2:
        minutes, seconds = parts
        return minutes * 60 + seconds
    return None


def match_team_size(match: Optional[Match]) -> int:
    if not match:
        return 0
    mode = (match.gamemode_name or match.game_mode or "").strip().lower()
    return RANKED_MODE_TEAM_SIZES.get(mode, 0)


def ranked_match_rejection_reason(
    match: Optional[Match],
    *,
    rules: Mapping[str, int | float],
) -> Optional[str]:
    if not match:
        return "Нет данных replay для проверки матча"
    has_ranked_signal = bool(match.elo_delta and match.elo_delta > 0) or any(
        participant.old_rank is not None or participant.new_rank is not None
        for participant in (match.participants or [])
        if not participant.is_observer
    )
    if match.is_valid is not True or not has_ranked_signal or not match_team_size(match):
        return "Матч не является валидным рейтинговым 1v1, 2v2, 3v3 или 4v4"
    duration_seconds = parse_match_duration_seconds(match.duration)
    if duration_seconds is None:
        return "Источник не передал длительность матча"
    minimum_seconds = int(rules["WAR_MIN_MATCH_DURATION_SECONDS"])
    effective_at = as_utc(settings.WAR_MIN_MATCH_DURATION_EFFECTIVE_AT)
    played_at = as_utc(match.match_date)
    if effective_at and (played_at is None or played_at < effective_at):
        minimum_seconds = max(minimum_seconds, settings.WAR_PREVIOUS_MIN_MATCH_DURATION_SECONDS)
    if duration_seconds < minimum_seconds:
        minimum_minutes = minimum_seconds // 60
        unit = "минуты" if minimum_minutes % 10 == 1 and minimum_minutes % 100 != 11 else "минут"
        return f"Матч короче {minimum_minutes} {unit}"
    return None


def ranked_1v1_rejection_reason(
    match: Optional[Match],
    *,
    rules: Mapping[str, int | float],
) -> Optional[str]:
    return ranked_match_rejection_reason(match, rules=rules)


def is_ranked_1v1_eligible(
    match: Match,
    *,
    rules: Mapping[str, int | float],
) -> bool:
    return ranked_match_rejection_reason(match, rules=rules) is None
