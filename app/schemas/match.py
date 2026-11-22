from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class MatchBase(BaseModel):
    match_id: str
    winner_player: str
    loser_player: str
    winner_faction: str
    loser_faction: str
    map_name: Optional[str] = None
    match_date: datetime
    duration: Optional[str] = None
    is_live: bool = False


class MatchCreate(MatchBase):
    pass


class MatchResponse(MatchBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class LiveMatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    match_id: str
    winner_player: str
    loser_player: str
    winner_faction: str
    loser_faction: str
    map_name: Optional[str] = None
    match_date: datetime
    duration: Optional[str] = None

class LadderStats(BaseModel):
    total_matches: int
    live_matches: int
    total_players: int
    last_update: datetime
