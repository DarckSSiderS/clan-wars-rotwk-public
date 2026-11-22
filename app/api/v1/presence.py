from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.auth import get_current_active_user
from app.core.time import utc_now
from app.database import get_db
from app.models.user import User
from app.schemas.presence import (
    OnlineRequestResult,
    PlayerPresenceList,
)
from app.services.presence_service import OnlineRequestCooldown, presence_service


router = APIRouter(prefix="/presence", tags=["presence"])


@router.get("", response_model=PlayerPresenceList)
def get_player_presence(
    user_ids: list[int] = Query(min_length=1, max_length=100),
    db: Session = Depends(get_db),
):
    normalized_ids = set(user_ids)
    existing_ids = {
        int(user_id)
        for (user_id,) in (
            db.query(User.id)
            .filter(User.id.in_(normalized_ids), User.is_active.is_(True))
            .all()
        )
    }
    return {
        "items": presence_service.get_many(db, existing_ids),
        "captured_at": utc_now(),
    }


@router.post(
    "/{target_user_id:int}/online-request",
    response_model=OnlineRequestResult,
)
def request_player_online(
    target_user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if target_user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя отправить запрос online самому себе",
        )
    target = (
        db.query(User)
        .filter(
            User.id == target_user_id,
            User.is_active.is_(True),
            User.is_claimed.is_(True),
        )
        .first()
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Активный игрок не найден",
        )
    try:
        return presence_service.request_online(
            db,
            requester=current_user,
            target=target,
        )
    except OnlineRequestCooldown as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Запрос online уже отправлен. Подождите минуту.",
            headers={
                "Retry-After": str(settings.ONLINE_REQUEST_COOLDOWN_SECONDS),
            },
        ) from error
