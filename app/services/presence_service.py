from __future__ import annotations

from threading import Lock
import time
from urllib.parse import quote

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.time import as_utc, utc_now
from app.models.auth_session import UserSession
from app.models.user import User
from app.services.notification_service import notification_service
from app.services.realtime_service import realtime_hub


class OnlineRequestCooldown(Exception):
    pass


class PresenceService:
    """Combines live WebSocket heartbeats with durable session activity."""

    def __init__(self) -> None:
        self._local_cooldowns: dict[str, float] = {}
        self._cooldown_lock = Lock()

    def get_many(self, db: Session, user_ids: set[int]) -> list[dict]:
        normalized_ids = {int(user_id) for user_id in user_ids}
        if not normalized_ids:
            return []

        online_ids = realtime_hub.online_user_ids(normalized_ids)
        rows = (
            db.query(
                UserSession.user_id,
                func.max(UserSession.last_seen_at).label("last_seen_at"),
            )
            .filter(
                UserSession.user_id.in_(normalized_ids),
                UserSession.is_impersonation.is_(False),
            )
            .group_by(UserSession.user_id)
            .all()
        )
        last_seen_by_user = {
            int(user_id): as_utc(last_seen_at)
            for user_id, last_seen_at in rows
            if last_seen_at is not None
        }
        captured_at = utc_now()
        return [
            {
                "user_id": user_id,
                "is_online": user_id in online_ids,
                "last_seen_at": (
                    captured_at
                    if user_id in online_ids
                    else last_seen_by_user.get(user_id)
                ),
            }
            for user_id in sorted(normalized_ids)
        ]

    def get_one(self, db: Session, user_id: int) -> dict:
        return self.get_many(db, {int(user_id)})[0]

    def request_online(
        self,
        db: Session,
        *,
        requester: User,
        target: User,
    ) -> dict:
        status = self.get_one(db, target.id)
        if status["is_online"]:
            return {
                "target_user_id": target.id,
                "status": "already_online",
                "is_online": True,
                "last_seen_at": status["last_seen_at"],
                "cooldown_seconds": settings.ONLINE_REQUEST_COOLDOWN_SECONDS,
            }

        cooldown_key = (
            f"{settings.PRESENCE_REDIS_KEY}:online-request:"
            f"{requester.id}:{target.id}"
        )
        acquired = realtime_hub.acquire_cooldown(
            cooldown_key,
            settings.ONLINE_REQUEST_COOLDOWN_SECONDS,
        )
        if acquired is None:
            acquired = self._acquire_local_cooldown(
                cooldown_key,
                settings.ONLINE_REQUEST_COOLDOWN_SECONDS,
            )
        if not acquired:
            raise OnlineRequestCooldown()

        notification_service.create(
            db,
            user_id=target.id,
            notification_type="online_request",
            title="Вас ждут online",
            message=f"{requester.username} спрашивает, вы online?",
            link_url=f"/profile/{quote(requester.username, safe='')}",
            entity_type="user",
            entity_id=requester.id,
        )
        return {
            "target_user_id": target.id,
            "status": "requested",
            "is_online": False,
            "last_seen_at": status["last_seen_at"],
            "cooldown_seconds": settings.ONLINE_REQUEST_COOLDOWN_SECONDS,
        }

    def _acquire_local_cooldown(self, key: str, seconds: int) -> bool:
        now = time.monotonic()
        with self._cooldown_lock:
            expires_at = self._local_cooldowns.get(key, 0.0)
            if expires_at > now:
                return False
            self._local_cooldowns[key] = now + seconds
            if len(self._local_cooldowns) > 1000:
                self._local_cooldowns = {
                    item_key: item_expiry
                    for item_key, item_expiry in self._local_cooldowns.items()
                    if item_expiry > now
                }
            return True


presence_service = PresenceService()
