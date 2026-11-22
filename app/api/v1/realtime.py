from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.database import SessionLocal
from app.services.realtime_service import realtime_hub
from app.services.session_service import InvalidSession, SessionService


router = APIRouter(prefix="/realtime", tags=["realtime"])


def _origin_is_allowed(origin: str | None) -> bool:
    if not origin or "*" in settings.CORS_ORIGINS:
        return True
    normalized = origin.rstrip("/")
    allowed = {str(value).rstrip("/") for value in settings.CORS_ORIGINS}
    return normalized in allowed


@router.websocket("/ws")
async def realtime_socket(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    if not _origin_is_allowed(origin):
        await websocket.accept()
        await websocket.close(code=4403, reason="Origin is not allowed")
        return

    token = websocket.cookies.get(settings.SESSION_COOKIE_NAME)
    try:
        with SessionLocal() as db:
            session = SessionService().resolve(db, token, touch=True)
            user_id = int(session.user_id)
            track_presence = not session.is_impersonation
            if not session.user.is_active and not getattr(
                session.user,
                "_is_admin_impersonation",
                False,
            ):
                raise InvalidSession()
    except InvalidSession:
        await websocket.accept()
        await websocket.close(code=4401, reason="Authentication required")
        return

    await realtime_hub.connect(
        user_id,
        websocket,
        mark_presence=track_presence,
    )
    await websocket.send_json({"type": "realtime.ready", "user_id": user_id})
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                try:
                    with SessionLocal() as db:
                        SessionService().resolve(db, token, touch=True)
                except InvalidSession:
                    await websocket.close(code=4401, reason="Session expired")
                    return
                if track_presence:
                    await realtime_hub.mark_online(user_id)
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        realtime_hub.disconnect(user_id, websocket)
