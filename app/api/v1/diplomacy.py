from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user, get_onboarded_active_user
from app.database import get_db
from app.models.user import User
from app.schemas.diplomacy import DiplomacyActionRequest, DiplomacyRelationResponse
from app.services.diplomacy_service import diplomacy_service


router = APIRouter(prefix="/clans", tags=["clan diplomacy"])


@router.get("/diplomacy", response_model=list[DiplomacyRelationResponse])
def list_diplomacy(
    clan_id: int | None = Query(default=None, ge=1),
    include_neutral: bool = False,
    _current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return diplomacy_service.list_relations(
        db,
        clan_id=clan_id,
        include_neutral=include_neutral,
    )


@router.post(
    "/{clan_id:int}/diplomacy/{other_clan_id:int}",
    response_model=DiplomacyRelationResponse,
)
def update_diplomacy(
    clan_id: int,
    other_clan_id: int,
    payload: DiplomacyActionRequest,
    current_user: User = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db),
):
    return diplomacy_service.act(
        db,
        actor_clan_id=clan_id,
        other_clan_id=other_clan_id,
        actor=current_user,
        action=payload.action,
        note=payload.note,
    )
