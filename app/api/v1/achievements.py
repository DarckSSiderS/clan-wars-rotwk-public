from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.core.auth import get_current_active_user, get_current_admin_user
from app.services.achievement_service import AchievementService, UserAchievementService
from app.schemas.achievement import (
    Achievement, AchievementCreate, AchievementUpdate,
    UserAchievement, UserAchievementCreate, UserAchievementUpdate,
    UserAchievementsSummary
)
from app.schemas.user import User

router = APIRouter(prefix="/achievements", tags=["achievements"])

# Достижения
@router.get("/", response_model=List[Achievement])
async def get_achievements(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить список достижений"""
    achievement_service = AchievementService()
    return achievement_service.get_achievements(db, skip=skip, limit=limit)

@router.get("/available/", response_model=List[Achievement])
async def get_available_achievements(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить доступные достижения"""
    achievement_service = AchievementService()
    return achievement_service.get_available_achievements(db)

@router.get("/category/{category}", response_model=List[Achievement])
async def get_achievements_by_category(
    category: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить достижения по категории"""
    achievement_service = AchievementService()
    return achievement_service.get_achievements_by_category(db, category)

@router.get("/type/{achievement_type}", response_model=List[Achievement])
async def get_achievements_by_type(
    achievement_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить достижения по типу"""
    achievement_service = AchievementService()
    return achievement_service.get_achievements_by_type(db, achievement_type)

@router.get("/{achievement_id:int}", response_model=Achievement)
async def get_achievement(
    achievement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить достижение по ID"""
    achievement_service = AchievementService()
    return achievement_service.get_achievement(db, achievement_id)

@router.post("/", response_model=Achievement)
async def create_achievement(
    achievement_data: AchievementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Создать новое достижение"""
    achievement_service = AchievementService()
    return achievement_service.create_achievement(db, achievement_data)

@router.put("/{achievement_id:int}", response_model=Achievement)
async def update_achievement(
    achievement_id: int,
    achievement_data: AchievementUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Обновить достижение"""
    achievement_service = AchievementService()
    return achievement_service.update_achievement(db, achievement_id, achievement_data)

@router.delete("/{achievement_id:int}")
async def delete_achievement(
    achievement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Удалить достижение"""
    achievement_service = AchievementService()
    achievement_service.delete_achievement(db, achievement_id)
    return {"message": "Достижение удалено"}

# Достижения пользователей
@router.get("/my-achievements/", response_model=List[UserAchievement])
async def get_my_achievements(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить достижения текущего пользователя"""
    user_achievement_service = UserAchievementService()
    return user_achievement_service.get_user_achievements(db, current_user.id)

@router.get("/my-achievements/completed/", response_model=List[UserAchievement])
async def get_my_completed_achievements(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить завершенные достижения текущего пользователя"""
    user_achievement_service = UserAchievementService()
    return user_achievement_service.get_completed_achievements(db, current_user.id)

@router.get("/my-achievements/in-progress/", response_model=List[UserAchievement])
async def get_my_in_progress_achievements(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить достижения в процессе выполнения"""
    user_achievement_service = UserAchievementService()
    return user_achievement_service.get_in_progress_achievements(db, current_user.id)

@router.get("/my-achievements/summary/", response_model=UserAchievementsSummary)
async def get_my_achievements_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить сводку по достижениям текущего пользователя"""
    user_achievement_service = UserAchievementService()
    return user_achievement_service.get_achievement_progress_summary(db, current_user.id)

@router.get("/users/{user_id}/achievements/", response_model=List[UserAchievement])
async def get_user_achievements(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить достижения пользователя"""
    user_achievement_service = UserAchievementService()
    return user_achievement_service.get_user_achievements(db, user_id)

@router.get("/users/{user_id}/achievements/completed/", response_model=List[UserAchievement])
async def get_user_completed_achievements(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить завершенные достижения пользователя"""
    user_achievement_service = UserAchievementService()
    return user_achievement_service.get_completed_achievements(db, user_id)

@router.get("/users/{user_id}/achievements/in-progress/", response_model=List[UserAchievement])
async def get_user_in_progress_achievements(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить достижения пользователя в процессе выполнения"""
    user_achievement_service = UserAchievementService()
    return user_achievement_service.get_in_progress_achievements(db, user_id)

@router.get("/users/{user_id}/achievements/summary/", response_model=UserAchievementsSummary)
async def get_user_achievements_summary(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить сводку по достижениям пользователя"""
    user_achievement_service = UserAchievementService()
    return user_achievement_service.get_achievement_progress_summary(db, user_id)

@router.get("/my-achievements/{achievement_id:int}", response_model=UserAchievement)
async def get_my_achievement(
    achievement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить достижение текущего пользователя"""
    user_achievement_service = UserAchievementService()
    return user_achievement_service.get_user_achievement(db, current_user.id, achievement_id)

# Управление прогрессом
@router.post("/my-achievements/{achievement_id:int}/create")
async def create_my_achievement(
    achievement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Создать достижение для текущего пользователя"""
    user_achievement_service = UserAchievementService()
    return user_achievement_service.create_user_achievement(db, current_user.id, achievement_id)

@router.put("/my-achievements/{achievement_id:int}/progress")
async def update_my_achievement_progress(
    achievement_id: int,
    progress: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Обновить прогресс достижения текущего пользователя"""
    user_achievement_service = UserAchievementService()
    return user_achievement_service.update_achievement_progress(db, current_user.id, achievement_id, progress)

@router.put("/my-achievements/{achievement_id:int}/complete")
async def complete_my_achievement(
    achievement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Завершить достижение текущего пользователя"""
    user_achievement_service = UserAchievementService()
    return user_achievement_service.complete_achievement(db, current_user.id, achievement_id) 
