from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PlayerPresence(BaseModel):
    user_id: int
    is_online: bool
    last_seen_at: datetime | None = None


class PlayerPresenceList(BaseModel):
    items: list[PlayerPresence]
    captured_at: datetime


class OnlineRequestResult(BaseModel):
    target_user_id: int
    status: Literal["already_online", "requested"]
    is_online: bool
    last_seen_at: datetime | None = None
    cooldown_seconds: int
