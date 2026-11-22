from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from enum import Enum

class QuestTypeEnum(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"

class QuestCategoryEnum(str, Enum):
    WINS = "wins"
    MATCHES_PLAYED = "matches_played"
    FACTION_WINS = "faction_wins"
    STREAK = "streak"

class QuestBase(BaseModel):
    title_key: str
    description_key: str
    quest_type: QuestTypeEnum
    category: QuestCategoryEnum
    target_value: int
    reward_coins: int
    reward_experience: int
    is_active: bool = True

class QuestCreate(QuestBase):
    pass

class QuestResponse(QuestBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str = ""  # Локализованное название
    description: str = ""  # Локализованное описание
    time_until_reset: str = ""  # Время до обновления
    created_at: datetime
    
class UserQuestBase(BaseModel):
    current_progress: int = 0
    is_completed: bool = False
    expires_at: datetime

class UserQuestCreate(UserQuestBase):
    user_id: int
    quest_id: int

class UserQuestResponse(UserQuestBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    quest_id: int
    is_claimed: bool = False
    completed_at: Optional[datetime] = None
    created_at: datetime
    quest: QuestResponse
    
class QuestProgressResponse(BaseModel):
    quest: QuestResponse
    user_quest: UserQuestResponse
    progress_percentage: float

class QuestRewardResponse(BaseModel):
    quest_id: int
    coins_earned: int
    experience_earned: int
    new_balance: int
    new_experience: int
    new_level: int
