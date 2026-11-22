from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user, get_onboarded_active_user
from app.core.time import utc_now
from app.database import get_db
from app.models.user import User
from app.services.preseason_service import PreseasonService


router = APIRouter(prefix='/preseason', tags=['preseason'])
service = PreseasonService()


class LandsPreview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selected: list[int] = Field(min_length=3, max_length=3, strict=True)


class LandsChoice(LandsPreview):
    expected_revision: int = Field(ge=1, strict=True)


class RelicsChoice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selected: list[str] = Field(min_length=2, max_length=2)
    expected_revision: int = Field(ge=1, strict=True)


def _invoke(db, operation, *, write=False, **kwargs):
    try:
        result = operation(db, now=utc_now(), **kwargs)
        if write:
            db.commit()
        return result
    except PermissionError as error:
        db.rollback()
        raise HTTPException(403, str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error


@router.get('/status')
def status(db: Session = Depends(get_db)):
    return service.status(db)


@router.get('/clans/{clan_id}')
def read(clan_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    return _invoke(db, service.read, clan_id=clan_id, actor_id=actor.id)


@router.post('/clans/{clan_id}/lands/preview')
def preview(clan_id: int, payload: LandsPreview, db: Session = Depends(get_db), actor: User = Depends(get_onboarded_active_user)):
    return _invoke(db, service.preview, clan_id=clan_id, actor_id=actor.id, **payload.model_dump())


@router.post('/clans/{clan_id}/lands')
def lands(clan_id: int, payload: LandsChoice, db: Session = Depends(get_db), actor: User = Depends(get_onboarded_active_user)):
    return _invoke(db, service.claim_lands, write=True, clan_id=clan_id, actor_id=actor.id, **payload.model_dump())


@router.post('/clans/{clan_id}/relics')
def relics(clan_id: int, payload: RelicsChoice, db: Session = Depends(get_db), actor: User = Depends(get_onboarded_active_user)):
    return _invoke(db, service.claim_relics, write=True, clan_id=clan_id, actor_id=actor.id, **payload.model_dump())
