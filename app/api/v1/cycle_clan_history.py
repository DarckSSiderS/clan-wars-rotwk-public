from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.database import get_db
from app.models.user import User
from app.services.cycle_clan_history_service import CycleClanHistoryService


router = APIRouter(prefix='/campaign/cycles/clans', tags=['campaign-clan-history'])


@router.get('/{clan_id}/history')
def clan_history(clan_id: int = Path(gt=0), db: Session = Depends(get_db),
                 _user: User = Depends(get_current_active_user)):
    try:
        return CycleClanHistoryService().read(db, clan_id=clan_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
