#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматический скрипт для сброса истекших заданий
Запускается по расписанию (например, каждый час)
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models.quest import UserQuest, Quest, QuestType
from app.models.user import User
from app.services.quest_service import QuestService

def auto_reset_expired_quests():
    """Автоматический сброс истекших заданий"""
    db = SessionLocal()
    
    try:
        now_utc = datetime.utcnow()
        now_moscow = now_utc + timedelta(hours=3)
        print(f"🕐 [{now_utc}] Автоматический сброс истекших заданий")
        print(f"🕐 [{now_moscow}] Московское время")
        
        # Получаем всех пользователей с истекшими заданиями
        users_with_expired_quests = db.query(User).join(UserQuest).filter(
            UserQuest.expires_at <= now_utc
        ).distinct().all()
        
        if not users_with_expired_quests:
            print(f"✅ Нет пользователей с истекшими заданиями")
            return
        
        print(f"🔧 Найдено {len(users_with_expired_quests)} пользователей с истекшими заданиями")
        
        quest_service = QuestService()
        total_reset_users = 0
        
        for user in users_with_expired_quests:
            # Удаляем истекшие задания
            expired_quests = db.query(UserQuest).filter(
                and_(
                    UserQuest.user_id == user.id,
                    UserQuest.expires_at <= now_utc
                )
            ).all()
            
            if expired_quests:
                for expired_quest in expired_quests:
                    db.delete(expired_quest)
            
            # Проверяем, есть ли активные задания
            active_daily_quests = db.query(UserQuest).join(Quest).filter(
                and_(
                    UserQuest.user_id == user.id,
                    Quest.quest_type == QuestType.DAILY,
                    UserQuest.expires_at > now_utc
                )
            ).count()
            
            active_weekly_quests = db.query(UserQuest).join(Quest).filter(
                and_(
                    UserQuest.user_id == user.id,
                    Quest.quest_type == QuestType.WEEKLY,
                    UserQuest.expires_at > now_utc
                )
            ).count()
            
            # Назначаем новые задания если нет активных
            if active_daily_quests == 0:
                quest_service.assign_daily_quests(db, user.id)
            
            if active_weekly_quests == 0:
                quest_service.assign_weekly_quests(db, user.id)
            
            total_reset_users += 1
        
        db.commit()
        print(f"✅ Сброшены задания для {total_reset_users} пользователей")
        
    except Exception as e:
        print(f"❌ Ошибка при автоматическом сбросе заданий: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    auto_reset_expired_quests()
