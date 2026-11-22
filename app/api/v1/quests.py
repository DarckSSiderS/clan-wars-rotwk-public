from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.core.auth import get_current_active_user, get_onboarded_active_user
from app.models.user import User as UserModel
from app.models.quest import QuestType
from app.models.localization import Localization
from app.schemas.quest import QuestResponse, UserQuestResponse, QuestProgressResponse, QuestRewardResponse
from app.services.quest_service import QuestService

router = APIRouter(prefix="/quests", tags=["quests"])

QUEST_TEXT_FALLBACKS = {
    "quest_daily_first_win": {
        "ru": "Первая победа дня",
        "eng": "First win of the day",
    },
    "quest_daily_first_win_desc": {
        "ru": "Победите в одном матче за день",
        "eng": "Win one match today",
    },
    "quest_daily_winner": {
        "ru": "Победитель дня",
        "eng": "Daily winner",
    },
    "quest_daily_winner_desc": {
        "ru": "Одержите пять побед за день",
        "eng": "Win five matches today",
    },
    "quest_daily_active_player": {
        "ru": "Активный игрок",
        "eng": "Active player",
    },
    "quest_daily_active_player_desc": {
        "ru": "Сыграйте три матча за день",
        "eng": "Play three matches today",
    },
    "quest_daily_win_streak": {
        "ru": "Победная серия",
        "eng": "Win streak",
    },
    "quest_daily_win_streak_desc": {
        "ru": "Одержите три победы подряд",
        "eng": "Win three matches in a row",
    },
    "quest_weekly_winner": {
        "ru": "Победитель недели",
        "eng": "Weekly winner",
    },
    "quest_weekly_winner_desc": {
        "ru": "Одержите десять побед за неделю",
        "eng": "Win ten matches this week",
    },
    "quest_weekly_player": {
        "ru": "Игрок недели",
        "eng": "Weekly player",
    },
    "quest_weekly_player_desc": {
        "ru": "Сыграйте двадцать пять матчей за неделю",
        "eng": "Play twenty-five matches this week",
    },
}


def _quest_text(localization, key: str, language: str) -> str:
    localized = getattr(localization, language, None) if localization else None
    if localized and localized != key:
        return localized
    fallback = QUEST_TEXT_FALLBACKS.get(key)
    if fallback:
        return fallback.get(language) or fallback["ru"]
    if key.startswith("quest_"):
        return "Задание"
    return key


def get_localized_quest_data(db: Session, quest, user_quest, language: str = "ru"):
    """Получить локализованные данные задания"""
    # Получаем локализованное название
    title_localization = db.query(Localization).filter(
        Localization.identifier == quest.title_key
    ).first()
    
    # Получаем локализованное описание
    description_localization = db.query(Localization).filter(
        Localization.identifier == quest.description_key
    ).first()
    
    # Вычисляем время до обновления
    # Оба времени должны быть в UTC для корректного сравнения
    now_utc = datetime.utcnow()
    expires_at = user_quest.expires_at
    
    # Убеждаемся, что оба datetime имеют одинаковый формат (без timezone)
    if expires_at.tzinfo is not None:
        expires_at = expires_at.replace(tzinfo=None)
    
    if expires_at > now_utc:
        time_diff = expires_at - now_utc
        total_seconds = int(time_diff.total_seconds())
        
        if quest.quest_type == QuestType.DAILY:
            # Для ежедневных заданий показываем часы и минуты
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            time_until_reset = f"{hours}ч {minutes}м"
        else:
            # Для еженедельных заданий показываем дни и часы
            days = total_seconds // 86400
            remaining_seconds = total_seconds % 86400
            hours = remaining_seconds // 3600
            time_until_reset = f"{days}д {hours}ч"
    else:
        time_until_reset = "Истекло"
    
    return {
        "title": _quest_text(title_localization, quest.title_key, language),
        "description": _quest_text(
            description_localization,
            quest.description_key,
            language,
        ),
        "time_until_reset": time_until_reset
    }

@router.get("/daily", response_model=List[QuestProgressResponse])
async def get_daily_quests(
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    language: str = "ru"
):
    """Получить ежедневные задания пользователя"""
    quest_service = QuestService()
    
    # Сбрасываем истекшие задания и назначаем новые
    quest_service.reset_expired_quests(db, current_user.id)
    
    # Обновляем прогресс заданий
    quest_service.update_quest_progress(db, current_user.id)
    
    # Получаем задания пользователя
    user_quests = quest_service.get_user_quests(db, current_user.id, QuestType.DAILY)
    
    result = []
    for user_quest in user_quests:
        progress_percentage = (user_quest.current_progress / user_quest.quest.target_value) * 100
        
        # Получаем локализованные данные
        localized_data = get_localized_quest_data(db, user_quest.quest, user_quest, language)
        
        # Создаем объект quest с локализованными данными
        quest_data = QuestResponse(
            id=user_quest.quest.id,
            title_key=user_quest.quest.title_key,
            description_key=user_quest.quest.description_key,
            title=localized_data["title"],
            description=localized_data["description"],
            time_until_reset=localized_data["time_until_reset"],
            quest_type=user_quest.quest.quest_type.value,
            category=user_quest.quest.category.value,
            target_value=user_quest.quest.target_value,
            reward_coins=user_quest.quest.reward_coins,
            reward_experience=user_quest.quest.reward_experience,
            is_active=user_quest.quest.is_active,
            created_at=user_quest.quest.created_at
        )
        
        result.append(QuestProgressResponse(
            quest=quest_data,
            user_quest=user_quest,
            progress_percentage=progress_percentage
        ))
    
    return result

@router.get("/weekly", response_model=List[QuestProgressResponse])
async def get_weekly_quests(
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    language: str = "ru"
):
    """Получить еженедельные задания пользователя"""
    quest_service = QuestService()
    
    # Сбрасываем истекшие задания и назначаем новые
    quest_service.reset_expired_quests(db, current_user.id)
    
    # Обновляем прогресс заданий
    quest_service.update_quest_progress(db, current_user.id)
    
    # Получаем задания пользователя
    user_quests = quest_service.get_user_quests(db, current_user.id, QuestType.WEEKLY)
    
    result = []
    for user_quest in user_quests:
        progress_percentage = (user_quest.current_progress / user_quest.quest.target_value) * 100
        
        # Получаем локализованные данные
        localized_data = get_localized_quest_data(db, user_quest.quest, user_quest, language)
        
        # Создаем объект quest с локализованными данными
        quest_data = QuestResponse(
            id=user_quest.quest.id,
            title_key=user_quest.quest.title_key,
            description_key=user_quest.quest.description_key,
            title=localized_data["title"],
            description=localized_data["description"],
            time_until_reset=localized_data["time_until_reset"],
            quest_type=user_quest.quest.quest_type.value,
            category=user_quest.quest.category.value,
            target_value=user_quest.quest.target_value,
            reward_coins=user_quest.quest.reward_coins,
            reward_experience=user_quest.quest.reward_experience,
            is_active=user_quest.quest.is_active,
            created_at=user_quest.quest.created_at
        )
        
        result.append(QuestProgressResponse(
            quest=quest_data,
            user_quest=user_quest,
            progress_percentage=progress_percentage
        ))
    
    return result

@router.post("/claim/{quest_id}", response_model=QuestRewardResponse)
async def claim_quest_reward(
    quest_id: int,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db)
):
    """Получить награду за задание"""
    quest_service = QuestService()
    
    result = quest_service.claim_quest_reward(db, current_user.id, quest_id)
    if not result:
        raise HTTPException(status_code=404, detail="Задание не найдено или не завершено")
    
    return QuestRewardResponse(
        quest_id=result["quest_id"],
        coins_earned=result["coins_earned"],
        experience_earned=result["experience_earned"],
        new_balance=result["new_balance"],
        new_experience=result["level_info"]["total_experience"],
        new_level=result["level_info"]["new_level"]
    )

@router.post("/refresh-daily")
async def refresh_daily_quests(
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db)
):
    """Обновить ежедневные задания"""
    quest_service = QuestService()
    assigned_quests = quest_service.assign_daily_quests(db, current_user.id)
    
    return {
        "message": f"Назначено {len(assigned_quests)} новых ежедневных заданий",
        "assigned_count": len(assigned_quests)
    }

@router.post("/refresh-weekly")
async def refresh_weekly_quests(
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db)
):
    """Обновить еженедельные задания"""
    quest_service = QuestService()
    assigned_quests = quest_service.assign_weekly_quests(db, current_user.id)
    
    return {
        "message": f"Назначено {len(assigned_quests)} новых еженедельных заданий",
        "assigned_count": len(assigned_quests)
    }

@router.post("/update-progress")
async def update_quest_progress(
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db)
):
    """Обновить прогресс заданий пользователя на основе матчей"""
    summary = QuestService().update_quest_progress_summary(db, current_user.id)

    if summary["active_count"] == 0:
        return {"message": "Нет активных заданий для обновления"}

    if summary["stats"]["total_matches"] == 0 and summary["updated_count"] == 0:
        return {"message": "Нет матчей за сегодня"}

    if summary["updated_count"] > 0:
        return {
            "message": (
                f"Обновлено {summary['updated_count']} заданий, "
                f"завершено {summary['completed_count']}"
            ),
            "updated_count": summary["updated_count"],
            "completed_count": summary["completed_count"],
            "stats": summary["stats"],
        }

    return {"message": "Прогресс не изменился"}
