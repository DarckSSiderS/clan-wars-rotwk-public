from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DirectConversationUser(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


class DirectMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class DirectMessageResponse(BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    sender_username: str
    body: str
    created_at: datetime
    read_at: Optional[datetime] = None


class DirectConversationResponse(BaseModel):
    id: int
    counterpart: DirectConversationUser
    last_message: Optional[DirectMessageResponse] = None
    unread_count: int = 0
    created_at: datetime
    updated_at: datetime


class DirectMessageListResponse(BaseModel):
    conversation: DirectConversationResponse
    messages: list[DirectMessageResponse] = Field(default_factory=list)
    total: int


class MessageReportCreate(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class MessageOperationResult(BaseModel):
    ok: bool = True
