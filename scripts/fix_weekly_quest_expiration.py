#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для исправления времени истечения еженедельных заданий
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

def fix_weekly_quest_expiration():
    """Исправить время истечения еженедельных заданий"""
    db = SessionLocal()
    
    try:
        now_utc = datetime.utcnow()
        now_moscow = now_utc + timedelta(hours=3)
        print(f"🕐 [{now_utc}] Исправление времени истечения еженедельных заданий")
        print(f"🕐 [{now_moscow}] Московское время")
        
        # Получаем все еженедельные задания
        weekly_quests = db.query(UserQuest).join(Quest).filter(
            Quest.quest_type == QuestType.WEEKLY
        ).all()
        
        if not weekly_quests:
            print("✅ Нет еженедельных заданий для исправления")
            return
        
        print(f"🔧 Найдено {len(weekly_quests)} еженедельных заданий для проверки")
        
        fixed_count = 0
        
        for user_quest in weekly_quests:
            old_expires_at = user_quest.expires_at
            
            # Убираем timezone info для корректного сравнения
            if old_expires_at.tzinfo is not None:
                old_expires_at = old_expires_at.replace(tzinfo=None)
            
            # Вычисляем правильное время истечения для еженедельных заданий
            days_until_sunday = (6 - now_moscow.weekday()) % 7
            if days_until_sunday == 0:  # Если сегодня воскресенье
                days_until_sunday = 7  # Истекает в следующее воскресенье
            next_sunday_moscow = now_moscow + timedelta(days=days_until_sunday)
            new_expires_at_moscow = next_sunday_moscow.replace(hour=0, minute=0, second=0, microsecond=0)
            # Конвертируем обратно в UTC
            new_expires_at = new_expires_at_moscow - timedelta(hours=3)
            
            # Проверяем, нужно ли исправлять
            time_diff = abs((new_expires_at - old_expires_at).total_seconds())
            
            if time_diff > 3600:  # Если разница больше часа
                print(f"📝 Исправляем задание {user_quest.quest.title_key} для пользователя {user_quest.user.username}")
                print(f"   Старое время: {old_expires_at}")
                print(f"   Новое время: {new_expires_at}")
                print(f"   Разница: {time_diff // 3600}ч {(time_diff % 3600) // 60}м")
                
                user_quest.expires_at = new_expires_at
                fixed_count += 1
        
        if fixed_count > 0:
            db.commit()
            print(f"✅ Исправлено {fixed_count} еженедельных заданий")
        else:
            print("✅ Все еженедельные задания уже имеют правильное время истечения")
        
    except Exception as e:
        print(f"❌ Ошибка при исправлении еженедельных заданий: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_weekly_quest_expiration() 