"""Campaign ownership checks without importing runtime services."""

from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientPermissionsException
from app.models.campaign import CampaignSeason


INTERSEASON_MESSAGE = 'Межсезонье: сезон завершён. Итоги доступны в архиве сезонов.'


def interseason_season(db: Session) -> CampaignSeason | None:
    """No seasons is legacy bootstrap, not an implicit closed campaign."""
    if db.query(CampaignSeason.id).filter_by(status='active').first() is not None:
        return None
    latest = db.query(CampaignSeason).order_by(CampaignSeason.number.desc()).first()
    return latest if latest is not None and latest.status == 'completed' else None


def is_interseason(db: Session) -> bool:
    return interseason_season(db) is not None


def cycle_owns_campaign(db: Session) -> bool:
    """Match CycleRuntimeService ownership, including between seasons."""
    season = db.query(CampaignSeason).filter_by(status='active').first()
    if season is None:
        season = db.query(CampaignSeason).order_by(CampaignSeason.number.desc()).first()
    return bool(season and (season.rules_snapshot or {}).get('mechanics_version') == 'cycle_v1')


def require_legacy_economy(db: Session) -> None:
    if is_interseason(db):
        raise InsufficientPermissionsException(INTERSEASON_MESSAGE)
    if cycle_owns_campaign(db):
        raise InsufficientPermissionsException(
            'Legacy economy mutations are unavailable in a cycle_v1 campaign'
        )
