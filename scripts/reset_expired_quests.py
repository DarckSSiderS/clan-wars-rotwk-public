#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для принудительного сброса истекших заданий и назначения новых
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime
from app.database import SessionLocal
from app.models.quest import UserQuest, Quest, QuestType
from app.models.user import User
from app.services.quest_service import QuestService

def reset_expired_quests_for_user(db: Session, user_id: int, username: str):
    """Сбросить истекшие задания для конкретного пользователя"""
    print(f"🔧 Сброс истекших заданий для пользователя {username}...")
    
    now = datetime.utcnow()
    
    # Получаем истекшие задания
    expired_quests = db.query(UserQuest).filter(
        and_(
            UserQuest.user_id == user_id,
            UserQuest.expires_at <= now
        )
    ).all()
    
    if not expired_quests:
        print(f"✅ У пользователя {username} нет истекших заданий")
        return
    
    print(f"🗑️ Удаляем {len(expired_quests)} истекших заданий...")
    
    # Удаляем истекшие задания
    for expired_quest in expired_quests:
        db.delete(expired_quest)
    
    # Проверяем, есть ли активные задания
    active_daily_quests = db.query(UserQuest).join(Quest).filter(
        and_(
            UserQuest.user_id == user_id,
            Quest.quest_type == QuestType.DAILY,
            UserQuest.expires_at > now
        )
    ).count()
    
    active_weekly_quests = db.query(UserQuest).join(Quest).filter(
        and_(
            UserQuest.user_id == user_id,
            Quest.quest_type == QuestType.WEEKLY,
            UserQuest.expires_at > now
        )
    ).count()
    
    print(f"📊 Активных заданий: ежедневных - {active_daily_quests}, еженедельных - {active_weekly_quests}")
    
    # Назначаем новые задания если нет активных
    quest_service = QuestService()
    new_daily_quests = []
    new_weekly_quests = []
    
    if active_daily_quests == 0:
        print(f"📅 Назначаем новые ежедневные задания...")
        new_daily_quests = quest_service.assign_daily_quests(db, user_id)
        print(f"✅ Назначено {len(new_daily_quests)} ежедневных заданий")
    
    if active_weekly_quests == 0:
        print(f"📅 Назначаем новые еженедельные задания...")
        new_weekly_quests = quest_service.assign_weekly_quests(db, user_id)
        print(f"✅ Назначено {len(new_weekly_quests)} еженедельных заданий")
    
    db.commit()
    
    total_new = len(new_daily_quests) + len(new_weekly_quests)
    if total_new > 0:
        print(f"🎉 Пользователю {username} назначено {total_new} новых заданий")
    else:
        print(f"ℹ️ Пользователю {username} не назначено новых заданий (уже есть активные)")

def reset_all_expired_quests():
    """Сбросить истекшие задания для всех пользователей"""
    db = SessionLocal()
    
    try:
        # Получаем всех пользователей с истекшими заданиями
        now = datetime.utcnow()
        users_with_expired_quests = db.query(User).join(UserQuest).filter(
            UserQuest.expires_at <= now
        ).distinct().all()
        
        if not users_with_expired_quests:
            print("✅ Нет пользователей с истекшими заданиями")
            return
        
        print(f"🔧 Найдено {len(users_with_expired_quests)} пользователей с истекшими заданиями")
        
        for user in users_with_expired_quests:
            reset_expired_quests_for_user(db, user.id, user.username)
            print("-" * 50)
        
        print("🎉 Сброс истекших заданий завершен!")
        
    except Exception as e:
        print(f"❌ Ошибка при сбросе заданий: {e}")
        db.rollback()
    finally:
        db.close()

def reset_quests_for_specific_user(username: str):
    """Сбросить задания для конкретного пользователя"""
    db = SessionLocal()
    
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            print(f"❌ Пользователь {username} не найден")
            return
        
        reset_expired_quests_for_user(db, user.id, username)
        
    except Exception as e:
        print(f"❌ Ошибка при сбросе заданий: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        username = sys.argv[1]
        print(f"🔧 Сброс заданий для пользователя: {username}")
        reset_quests_for_specific_user(username)
    else:
        print("🔧 Сброс истекших заданий для всех пользователей")
        reset_all_expired_quests() 