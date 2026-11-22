from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class QuestType(enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"

class QuestCategory(enum.Enum):
    WINS = "wins"
    MATCHES_PLAYED = "matches_played"
    FACTION_WINS = "faction_wins"
    STREAK = "streak"

class Quest(Base):
    __tablename__ = "quests"
    
    id = Column(Integer, primary_key=True, index=True)
    title_key = Column(String(255), nullable=False)  # Ключ для локализации названия
    description_key = Column(String(255), nullable=False)  # Ключ для локализации описания
    quest_type = Column(Enum(QuestType), nullable=False)
    category = Column(Enum(QuestCategory), nullable=False)
    target_value = Column(Integer, nullable=False)  # Целевое значение (например, 5 побед)
    reward_coins = Column(Integer, nullable=False)  # Награда в монетах
    reward_experience = Column(Integer, nullable=False)  # Награда в опыте
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Связи
    user_quests = relationship("UserQuest", back_populates="quest")

class UserQuest(Base):
    __tablename__ = "user_quests"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    quest_id = Column(Integer, ForeignKey("quests.id"), nullable=False)
    current_progress = Column(Integer, default=0)  # Текущий прогресс
    is_completed = Column(Boolean, default=False)  # Завершено ли задание
    is_claimed = Column(Boolean, default=False)  # Получена ли награда
    completed_at = Column(DateTime(timezone=True), nullable=True)  # Когда завершено
    expires_at = Column(DateTime(timezone=True), nullable=False)  # Когда истекает
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Связи
    user = relationship("User", back_populates="user_quests")
    quest = relationship("Quest", back_populates="user_quests") 