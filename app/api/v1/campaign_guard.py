from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.campaign_mode import INTERSEASON_MESSAGE, is_interseason
from app.services.campaign_pause_service import CampaignPauseService


def require_campaign_running(db: Session) -> None:
    if is_interseason(db):
        raise HTTPException(status_code=409, detail=INTERSEASON_MESSAGE)
    if CampaignPauseService.is_paused(db):
        raise HTTPException(
            status_code=409,
            detail="Кампания приостановлена администратором",
        )
