from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class AchievementBase(BaseModel):
    name: str
    description: str
    icon: str
    category: str
    rarity: str = "common"
    points: int = 0
    requirement_type: str
    requirement_value: int
    target_value: int
    reward_amount: Optional[int] = 0
    achievement_type: Optional[str] = None

class AchievementCreate(AchievementBase):
    is_available: bool = True

class AchievementUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    category: Optional[str] = None
    rarity: Optional[str] = None
    points: Optional[int] = None
    requirement_type: Optional[str] = None
    requirement_value: Optional[int] = None
    target_value: Optional[int] = None
    reward_amount: Optional[int] = None
    achievement_type: Optional[str] = None
    is_available: Optional[bool] = None

class Achievement(AchievementBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_available: bool
    created_at: datetime

class UserAchievementBase(BaseModel):
    progress: int = 0
    is_completed: bool = False

class UserAchievementCreate(UserAchievementBase):
    pass

class UserAchievementUpdate(BaseModel):
    progress: Optional[int] = None
    is_completed: Optional[bool] = None

class UserAchievement(UserAchievementBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    achievement_id: int
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    achievement: Achievement

class AchievementProgress(BaseModel):
    achievement_id: int
    progress: int
    is_completed: bool

class UserAchievementsSummary(BaseModel):
    total_achievements: int
    completed_achievements: int
    total_points: int
    completion_percentage: float
