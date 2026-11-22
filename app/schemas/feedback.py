from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


FeedbackCategory = Literal["bug", "suggestion", "question", "other"]
FeedbackStatus = Literal["new", "in_progress", "waiting_user", "resolved", "closed"]
FeedbackPriority = Literal["low", "normal", "high", "critical"]


class FeedbackTicketCreate(BaseModel):
    category: FeedbackCategory
    title: str = Field(min_length=5, max_length=160)
    description: str = Field(min_length=10, max_length=5000)
    reproduction_steps: Optional[str] = Field(default=None, max_length=3000)
    expected_result: Optional[str] = Field(default=None, max_length=3000)
    actual_result: Optional[str] = Field(default=None, max_length=3000)
    source_path: Optional[str] = Field(default=None, max_length=500)
    user_agent: Optional[str] = Field(default=None, max_length=500)

    @field_validator(
        "title",
        "description",
        "reproduction_steps",
        "expected_result",
        "actual_result",
        "source_path",
        "user_agent",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value):
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("source_path")
    @classmethod
    def normalize_source_path(cls, value):
        if value is None:
            return None
        path = value.split("?", 1)[0].split("#", 1)[0]
        if not path.startswith("/"):
            return None
        return path[:500]

    @model_validator(mode="after")
    def validate_bug_details(self):
        if self.category == "bug" and not (self.actual_result or self.reproduction_steps):
            raise ValueError("Для ошибки укажите шаги воспроизведения или фактический результат")
        return self


class FeedbackReplyCreate(BaseModel):
    body: str = Field(min_length=2, max_length=4000)

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value):
        return value.strip()


class FeedbackAdminUpdate(BaseModel):
    status: Optional[FeedbackStatus] = None
    priority: Optional[FeedbackPriority] = None
    assign_to_me: Optional[bool] = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно изменение")
        return self


class FeedbackMessageResponse(BaseModel):
    id: int
    author_id: Optional[int] = None
    author_name: str
    body: str
    is_admin: bool
    created_at: datetime


class FeedbackTicketResponse(BaseModel):
    id: int
    reference: str
    reporter_id: int
    reporter_name: str
    assigned_admin_id: Optional[int] = None
    assigned_admin_name: Optional[str] = None
    category: FeedbackCategory
    title: str
    description: str
    reproduction_steps: Optional[str] = None
    expected_result: Optional[str] = None
    actual_result: Optional[str] = None
    attachment_url: Optional[str] = None
    source_path: Optional[str] = None
    user_agent: Optional[str] = None
    status: FeedbackStatus
    priority: FeedbackPriority
    admin_unread: bool
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    messages: list[FeedbackMessageResponse] = Field(default_factory=list)


class FeedbackSummary(BaseModel):
    total: int
    unread: int
    new: int
    in_progress: int
    critical: int


class FeedbackListResponse(BaseModel):
    items: list[FeedbackTicketResponse]
    total: int
    summary: FeedbackSummary
