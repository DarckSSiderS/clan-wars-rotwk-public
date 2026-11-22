from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user
from app.core.time import utc_now
from app.database import get_db
from app.models.user import User
from app.services.cycle_administration_service import CycleAdministrationService


router = APIRouter(prefix='/admin', tags=['cycle-administration'])
service = CycleAdministrationService()


class RecoveryInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(gt=0, strict=True)
    command_id: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=3, max_length=500)


@router.get('/diagnostics')
def diagnostics(db: Session = Depends(get_db), _admin: User = Depends(get_current_admin_user)):
    return service.diagnostics(db, now=utc_now())


@router.post('/cycles/{cycle_id}/recover-preparation')
def recover_preparation(cycle_id: int, payload: RecoveryInput, db: Session = Depends(get_db),
                        admin: User = Depends(get_current_admin_user)):
    try:
        result = service.recover_preparation(db, cycle_id=cycle_id, actor_user_id=admin.id,
            now=utc_now(), **payload.model_dump())
        db.commit()
        return result
    except ValueError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error
