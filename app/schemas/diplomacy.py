from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


DiplomacyAction = Literal[
    "propose_alliance",
    "accept_alliance",
    "reject_alliance",
    "declare_hostility",
    "set_neutral",
]


class DiplomacyActionRequest(BaseModel):
    action: DiplomacyAction
    note: Optional[str] = Field(default=None, max_length=500)


class DiplomacyClanSummary(BaseModel):
    id: int
    name: str
    avatar_url: Optional[str] = None
    map_color: Optional[str] = None


class DiplomacyEventResponse(BaseModel):
    id: int
    actor_clan_id: Optional[int] = None
    actor_clan_name: Optional[str] = None
    previous_status: str
    new_status: str
    note: Optional[str] = None
    created_at: datetime


class DiplomacyRelationResponse(BaseModel):
    id: int
    clan_low: DiplomacyClanSummary
    clan_high: DiplomacyClanSummary
    status: str
    requested_by_clan_id: Optional[int] = None
    updated_at: datetime
    events: list[DiplomacyEventResponse] = Field(default_factory=list)
