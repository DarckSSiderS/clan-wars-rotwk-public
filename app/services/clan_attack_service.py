from datetime import datetime, timedelta
from typing import Optional

from app.core.time import as_utc, utc_now


def serialize_attack_point_status(status, *, cooldown_hours: int) -> dict:
    """Compatibility shape plus the multi-point fields used by new clients."""
    current_time = utc_now()
    next_attack_at = status.next_attack_at
    remaining_seconds = 0
    if next_attack_at and next_attack_at > current_time:
        remaining_seconds = max(1, int((next_attack_at - current_time).total_seconds()))
    return {
        "attack_available": status.available > 0,
        "next_attack_at": next_attack_at,
        "attack_cooldown_seconds": remaining_seconds,
        "attack_cooldown_duration_seconds": int(
            timedelta(hours=cooldown_hours).total_seconds()
        ),
        "attack_capacity": status.capacity,
        "attack_points_available": status.available,
        "attack_points_recovering": status.recovering,
        "attack_points_blocked": status.blocked,
        "attack_point_recoveries": status.recoveries,
    }


def normalize_utc(value: Optional[datetime]) -> Optional[datetime]:
    return as_utc(value)


def get_clan_attack_status(
    next_attack_at: Optional[datetime],
    *,
    cooldown_hours: int,
    now: Optional[datetime] = None,
) -> dict:
    current_time = normalize_utc(now) or utc_now()
    available_at = normalize_utc(next_attack_at)
    cooldown_seconds = int(timedelta(hours=cooldown_hours).total_seconds())
    remaining_seconds = 0
    if available_at and available_at > current_time:
        remaining_seconds = max(1, int((available_at - current_time).total_seconds()))

    return {
        "attack_available": remaining_seconds == 0,
        "next_attack_at": next_attack_at,
        "attack_cooldown_seconds": remaining_seconds,
        "attack_cooldown_duration_seconds": cooldown_seconds,
    }


def get_next_attack_at(
    *,
    cooldown_hours: int,
    now: Optional[datetime] = None,
) -> datetime:
    return (normalize_utc(now) or utc_now()) + timedelta(hours=cooldown_hours)
