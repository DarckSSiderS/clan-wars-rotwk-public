from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user
from app.database import get_db
from app.models.user import User
from app.services.cycle_admin_economy_service import CycleAdminEconomyService
from app.services.cycle_economy import RESOURCE_NAMES, Resources


router = APIRouter(prefix='/admin/clans', tags=['admin-cycle-economy'])


class TreasuryCorrectionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    season_id: int = Field(gt=0, strict=True)
    expected_revision: int = Field(gt=0, strict=True)
    command_id: str = Field(min_length=1, max_length=120, strict=True)
    reason: str = Field(min_length=3, max_length=2000, strict=True)
    wallet: dict[str, str | int]

    @field_validator('command_id', 'reason', mode='before')
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('wallet', mode='before')
    @classmethod
    def validate_wallet(cls, value):
        if not isinstance(value, dict) or set(value) != set(RESOURCE_NAMES):
            raise ValueError('A complete seasonal resource wallet is required')
        try:
            balance = Resources(**value)
        except (TypeError, ValueError) as error:
            raise ValueError(str(error)) from error
        if any(len(str(value[key])) > 80 for key in RESOURCE_NAMES):
            raise ValueError('Resource amount is too long')
        if any(abs(getattr(balance, key).as_tuple().exponent) > 36
               or getattr(balance, key).adjusted() > 36 for key in RESOURCE_NAMES):
            raise ValueError('Resource amount exceeds supported precision')
        return {key: format(getattr(balance, key), 'f') for key in RESOURCE_NAMES}


def _run(db, operation):
    try:
        result = operation()
        db.commit()
        return result
    except PermissionError as error:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception:
        db.rollback()
        raise


@router.get('/{clan_id:int}/cycle-economy')
def get_treasury(clan_id: int, db: Session = Depends(get_db),
                 admin: User = Depends(get_current_admin_user)):
    return _run(db, lambda: CycleAdminEconomyService().read(db, clan_id=clan_id, actor_id=admin.id))


@router.patch('/{clan_id:int}/cycle-economy')
def correct_treasury(clan_id: int, payload: TreasuryCorrectionInput,
                     db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    return _run(db, lambda: CycleAdminEconomyService().correct(
        db, clan_id=clan_id, actor_id=admin.id, **payload.model_dump()))
