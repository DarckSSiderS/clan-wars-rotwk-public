from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.core.auth import get_current_active_user
from app.database import get_db
from app.models.discord import DiscordLink
from app.models.user import User
from app.services.discord_link_service import LinkError, consume_link_code, unlink

router = APIRouter(prefix="/discord", tags=["discord"])


class LinkInput(BaseModel):
    code: str = Field(min_length=20, max_length=100)


def eligible_user(user: User = Depends(get_current_active_user)):
    if getattr(user, "_is_admin_impersonation", False):
        raise HTTPException(403, "Выйдите из режима просмотра чужого аккаунта.")
    if not user.is_active or not user.is_claimed:
        raise HTTPException(403, "Требуется активный подтверждённый аккаунт.")
    return user


def mutation_guard(request: Request):
    if not settings.DISCORD_ENABLED:
        raise HTTPException(503, "Интеграция Discord пока не включена.")
    # Reject cross-site browser forms even when cookies are supplied.
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Подтвердите привязку на сайте ClanWar.")
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in {
        str(request.base_url).rstrip("/"),
        settings.DISCORD_SITE_URL.rstrip("/"),
    }:
        raise HTTPException(403, "Недопустимый источник запроса.")


@router.get("/link")
def link_status(
    response: Response, user=Depends(eligible_user), db: Session = Depends(get_db)
):
    response.headers["Cache-Control"] = "no-store"
    if not settings.DISCORD_ENABLED:
        return {"enabled": False, "discord_user_id": None}
    link = db.get(DiscordLink, user.id)
    return {"enabled": True, "discord_user_id": link.discord_user_id if link else None}


@router.post("/link", dependencies=[Depends(mutation_guard)])
def confirm_link(
    payload: LinkInput,
    response: Response,
    user=Depends(eligible_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        link = consume_link_code(db, user, payload.code)
    except LinkError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"enabled": True, "discord_user_id": link.discord_user_id}


@router.delete("/link", dependencies=[Depends(mutation_guard)], status_code=204)
def remove_link(user=Depends(eligible_user), db: Session = Depends(get_db)):
    unlink(db, user.id)
