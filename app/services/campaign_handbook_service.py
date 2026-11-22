"""Public handbook context, independent of the actual campaign mechanics."""

from sqlalchemy.orm import Session

from app.core.campaign_mode import interseason_season


def decorate_public_rules_snapshot(
    db: Session, snapshot: dict, *, season_id: int | None = None,
) -> dict:
    if season_id is not None:
        return snapshot
    # The same read-only predicate as is_interseason, with its predecessor row.
    previous = interseason_season(db)
    if previous is None:
        return snapshot
    return {
        **snapshot,
        'guide': {
            'mechanics_version': 'cycle_v1',
            'status': 'upcoming',
            'previous_season_id': previous.id,
        },
    }
