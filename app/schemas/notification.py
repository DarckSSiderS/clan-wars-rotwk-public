from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Notification(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    notification_type: str
    title: str
    message: str
    link_url: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    created_at: datetime
    read_at: Optional[datetime] = None

class NotificationList(BaseModel):
    items: list[Notification]
    total: int = Field(ge=0)
    unread_count: int = Field(ge=0)


class NotificationUnreadCount(BaseModel):
    unread_count: int = Field(ge=0)


class NotificationReadAllResult(BaseModel):
    updated: int = Field(ge=0)
