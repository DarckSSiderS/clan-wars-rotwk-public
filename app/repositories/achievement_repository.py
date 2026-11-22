from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.achievement import Achievement, UserAchievement
from app.repositories.base import BaseRepository


class AchievementRepository(BaseRepository[Achievement]):
    """Репозиторий для работы с достижениями"""
    
    def __init__(self):
        super().__init__(Achievement)
    
    def get_available_achievements(self, db: Session) -> List[Achievement]:
        """Получить все доступные достижения"""
        return db.query(Achievement).filter(Achievement.is_available == True).all()
    
    def get_achievements_by_category(self, db: Session, category: str) -> List[Achievement]:
        """Получить достижения по категории"""
        return db.query(Achievement).filter(Achievement.category == category).all()
    
    def get_achievements_by_type(self, db: Session, achievement_type: str) -> List[Achievement]:
        """Получить достижения по типу"""
        return db.query(Achievement).filter(Achievement.achievement_type == achievement_type).all()


class UserAchievementRepository(BaseRepository[UserAchievement]):
    """Репозиторий для работы с достижениями пользователей"""
    
    def __init__(self):
        super().__init__(UserAchievement)
    
    def get_user_achievements(self, db: Session, user_id: int) -> List[UserAchievement]:
        """Получить актуальные достижения пользователя."""
        return (
            db.query(UserAchievement)
            .join(Achievement, Achievement.id == UserAchievement.achievement_id)
            .filter(
                UserAchievement.user_id == user_id,
                Achievement.is_available == True,
                Achievement.is_active == True,
            )
            .order_by(Achievement.category, Achievement.achievement_type, Achievement.target_value)
            .all()
        )
    
    def get_user_achievement_by_achievement(self, db: Session, user_id: int, achievement_id: int) -> Optional[UserAchievement]:
        """Получить достижение пользователя по достижению"""
        return db.query(UserAchievement).filter(
            and_(
                UserAchievement.user_id == user_id,
                UserAchievement.achievement_id == achievement_id
            )
        ).first()
    
    def get_completed_achievements(self, db: Session, user_id: int) -> List[UserAchievement]:
        """Получить завершенные достижения пользователя"""
        return db.query(UserAchievement).join(Achievement).filter(
            and_(
                UserAchievement.user_id == user_id,
                UserAchievement.is_completed == True,
                Achievement.is_available == True,
                Achievement.is_active == True,
            )
        ).all()
    
    def get_in_progress_achievements(self, db: Session, user_id: int) -> List[UserAchievement]:
        """Получить достижения в процессе выполнения"""
        return db.query(UserAchievement).join(Achievement).filter(
            and_(
                UserAchievement.user_id == user_id,
                UserAchievement.is_completed == False,
                Achievement.is_available == True,
                Achievement.is_active == True,
            )
        ).all()
