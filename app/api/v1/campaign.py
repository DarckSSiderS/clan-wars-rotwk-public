from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import get_current_active_user, get_current_admin_user
from app.database import get_db
from app.models.user import User
from app.services.campaign_history_service import CampaignHistoryService
from app.services.campaign_handbook_service import decorate_public_rules_snapshot


router = APIRouter(prefix="/campaign", tags=["campaign"])
service = CampaignHistoryService()


class CycleSeasonStartInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)
    command_id: str = Field(min_length=1, max_length=120)
    previous_season_id: int = Field(ge=0, strict=True)


@router.get('/map/preparation')
def upcoming_map(db: Session = Depends(get_db)):
    from app.services.cycle_season_launch_service import CycleSeasonLaunchService
    try:
        return CycleSeasonLaunchService().preparation(db)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post('/seasons/start')
def start_cycle_season(payload: CycleSeasonStartInput, db: Session = Depends(get_db),
                       admin: User = Depends(get_current_admin_user)):
    from app.core.time import utc_now
    from app.services.cycle_season_launch_service import CycleSeasonLaunchService
    try:
        result = CycleSeasonLaunchService().start(db, actor_user_id=admin.id, now=utc_now(), **payload.model_dump())
        db.commit()
        return result
    except PermissionError as error:
        db.rollback()
        raise HTTPException(403, str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error

from app.api.v1.cycle_campaign import router as cycle_router
from app.api.v1.season_archive import router as archive_router
from app.api.v1.preseason import router as preseason_router

router.include_router(cycle_router)
router.include_router(archive_router)
router.include_router(preseason_router)


@router.get("/influence-history")
def get_influence_history(
    clan_id: int | None = Query(None, ge=1),
    season_id: int | None = Query(None, ge=1),
    limit: int = Query(200, ge=1, le=500),
    _current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return service.influence_history(
        db,
        clan_id=clan_id,
        season_id=season_id,
        limit=limit,
    )


@router.get("/seasons")
def get_seasons(
    _current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return {"seasons": service.list_seasons(db)}


@router.get("/rules/public")
def get_public_campaign_rules(
    season_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
):
    try:
        result = service.public_rules_snapshot(db, season_id=season_id)
    except LookupError as error:
        raise HTTPException(
            status_code=503,
            detail="Правила кампании ещё не опубликованы",
        ) from error
    if result is None:
        raise HTTPException(status_code=404, detail="Сезон не найден")
    return decorate_public_rules_snapshot(db, result, season_id=season_id)


@router.get("/seasons/{season_id}")
def get_season(
    season_id: int,
    _current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    result = service.season_detail(db, season_id)
    if not result:
        raise HTTPException(status_code=404, detail="Сезон не найден")
    return result


@router.post("/seasons/current/complete")
def complete_current_season(
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    try:
        season = service.complete_active_season(db)
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not season:
        raise HTTPException(status_code=409, detail="Активный сезон не запущен")
    db.commit()
    return service.season_detail(db, season.id)
