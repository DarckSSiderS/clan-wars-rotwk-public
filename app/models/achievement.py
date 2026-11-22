from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Achievement(Base):
    __tablename__ = "achievements"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=False)
    icon = Column(String, nullable=False)  # Иконка достижения (FontAwesome класс)
    category = Column(String, nullable=False)  # combat, social, collection, etc.
    rarity = Column(String, default="common")  # common, rare, epic, legendary
    points = Column(Integer, default=0)  # Очки за достижение
    requirement_type = Column(String, nullable=False)  # wins, matches, faction_wins, etc.
    requirement_value = Column(Integer, nullable=False)  # Количество для получения
    target_value = Column(Integer, default=1)
    reward_amount = Column(Integer, default=0)
    achievement_type = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_available = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class UserAchievement(Base):
    __tablename__ = "user_achievements"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    achievement_id = Column(Integer, ForeignKey("achievements.id"), nullable=False)
    progress = Column(Integer, default=0)  # Текущий прогресс
    is_completed = Column(Boolean, default=False)  # Достижение получено
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Отношения
    user = relationship("User", back_populates="achievements")
    achievement = relationship("Achievement")
    
    # Уникальность: один пользователь может иметь только одну запись для каждого достижения
    __table_args__ = (
        UniqueConstraint('user_id', 'achievement_id', name='uq_user_achievement'),
    ) 
