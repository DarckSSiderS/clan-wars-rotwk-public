#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для исправления времени истечения заданий
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models.quest import UserQuest, Quest, QuestType
from app.models.user import User

def fix_quest_expiration():
    """Исправить время истечения всех заданий"""
    db = SessionLocal()
    
    try:
        now_utc = datetime.utcnow()
        print(f"🕐 Текущее время (UTC): {now_utc}")
        print("=" * 80)
        
        # Получаем все задания
        all_user_quests = db.query(UserQuest).all()
        
        if not all_user_quests:
            print("📝 Нет заданий для исправления")
            return
        
        print(f"🔧 Найдено {len(all_user_quests)} заданий для проверки")
        
        fixed_count = 0
        
        for user_quest in all_user_quests:
            quest = user_quest.quest
            old_expires_at = user_quest.expires_at
            
            # Убираем timezone info для корректного сравнения
            if old_expires_at.tzinfo is not None:
                old_expires_at = old_expires_at.replace(tzinfo=None)
            
            # Вычисляем правильное время истечения
            if quest.quest_type == QuestType.DAILY:
                # Ежедневные задания истекают в 23:59:59 UTC следующего дня
                tomorrow = now_utc + timedelta(days=1)
                new_expires_at = tomorrow.replace(hour=23, minute=59, second=59, microsecond=999999)
            else:  # WEEKLY
                # Еженедельные задания истекают в воскресенье в 23:59:59 UTC
                days_until_sunday = (6 - now_utc.weekday()) % 7
                if days_until_sunday == 0:  # Если сегодня воскресенье
                    days_until_sunday = 7  # Истекает в следующее воскресенье
                new_expires_at = now_utc + timedelta(days=days_until_sunday)
                new_expires_at = new_expires_at.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Проверяем, нужно ли исправлять
            time_diff = abs((new_expires_at - old_expires_at).total_seconds())
            
            if time_diff > 3600:  # Если разница больше часа
                print(f"🔧 Исправляем задание {quest.title_key} для пользователя {user_quest.user.username}")
                print(f"   Старое время: {old_expires_at}")
                print(f"   Новое время: {new_expires_at}")
                
                user_quest.expires_at = new_expires_at
                fixed_count += 1
        
        if fixed_count > 0:
            db.commit()
            print(f"✅ Исправлено {fixed_count} заданий")
        else:
            print("✅ Все задания уже имеют правильное время истечения")
    
    except Exception as e:
        print(f"❌ Ошибка при исправлении заданий: {e}")
        db.rollback()
    finally:
        db.close()

def reset_all_quests():
    """Полностью сбросить все задания и создать новые"""
    db = SessionLocal()
    
    try:
        print("🗑️ Удаляем все существующие задания...")
        
        # Удаляем все задания
        deleted_count = db.query(UserQuest).delete()
        db.commit()
        
        print(f"✅ Удалено {deleted_count} заданий")
        
        # Получаем всех пользователей
        users = db.query(User).all()
        print(f"👥 Найдено {len(users)} пользователей")
        
        # Создаем новые задания для каждого пользователя
        from app.services.quest_service import QuestService
        quest_service = QuestService()
        
        total_new_quests = 0
        
        for user in users:
            print(f"📅 Создаем задания для пользователя {user.username}...")
            
            daily_quests = quest_service.assign_daily_quests(db, user.id)
            weekly_quests = quest_service.assign_weekly_quests(db, user.id)
            
            total_new_quests += len(daily_quests) + len(weekly_quests)
            print(f"   Создано {len(daily_quests)} ежедневных и {len(weekly_quests)} еженедельных заданий")
        
        print(f"🎉 Всего создано {total_new_quests} новых заданий")
    
    except Exception as e:
        print(f"❌ Ошибка при сбросе заданий: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "reset":
        print("🔄 Полный сброс всех заданий")
        reset_all_quests()
    else:
        print("🔧 Исправление времени истечения заданий")
        fix_quest_expiration() 