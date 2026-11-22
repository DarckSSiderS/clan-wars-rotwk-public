#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Финальная проверка статуса заданий
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

def check_quests_final():
    """Финальная проверка статуса заданий"""
    db = SessionLocal()
    
    try:
        now_utc = datetime.utcnow()
        now_moscow = now_utc + timedelta(hours=3)
        print(f"🕐 [{now_utc}] Финальная проверка заданий")
        print(f"🕐 [{now_moscow}] Московское время")
        print("=" * 60)
        
        # Получаем всех пользователей с заданиями
        users_with_quests = db.query(User).join(UserQuest).distinct().all()
        
        if not users_with_quests:
            print("❌ Нет пользователей с заданиями")
            return
        
        print(f"👥 Найдено {len(users_with_quests)} пользователей с заданиями")
        print("=" * 60)
        
        for user in users_with_quests:
            print(f"👤 Пользователь: {user.username}")
            print("-" * 40)
            
            # Получаем все задания пользователя
            user_quests = db.query(UserQuest).filter(UserQuest.user_id == user.id).all()
            
            if not user_quests:
                print("   📝 Нет заданий")
                continue
            
            daily_quests = []
            weekly_quests = []
            
            for user_quest in user_quests:
                quest = user_quest.quest
                # Приводим к UTC для сравнения
                expires_at_utc = user_quest.expires_at.replace(tzinfo=None) if user_quest.expires_at.tzinfo else user_quest.expires_at
                is_expired = expires_at_utc <= now_utc
                time_left = expires_at_utc - now_utc
                
                quest_info = {
                    'id': quest.id,
                    'title': quest.title_key,
                    'progress': user_quest.current_progress,
                    'target': quest.target_value,
                    'completed': user_quest.is_completed,
                    'claimed': user_quest.is_claimed,
                    'expires_at': expires_at_utc,
                    'is_expired': is_expired,
                    'time_left': time_left
                }
                
                if quest.quest_type == QuestType.DAILY:
                    daily_quests.append(quest_info)
                else:
                    weekly_quests.append(quest_info)
            
            # Выводим ежедневные задания
            if daily_quests:
                print("   📅 Ежедневные задания:")
                for quest_info in daily_quests:
                    status = "✅ Завершено" if quest_info['completed'] else "🔄 В процессе"
                    if quest_info['claimed']:
                        status = "💰 Награда получена"
                    if quest_info['is_expired']:
                        status = "⏰ Истекло"
                    
                    time_str = "Истекло"
                    if not quest_info['is_expired']:
                        hours = int(quest_info['time_left'].total_seconds() // 3600)
                        minutes = int((quest_info['time_left'].total_seconds() % 3600) // 60)
                        time_str = f"{hours}ч {minutes}м"
                    
                    print(f"      • {quest_info['title']}: {quest_info['progress']}/{quest_info['target']} - {status} (истекает через {time_str})")
            
            # Выводим еженедельные задания
            if weekly_quests:
                print("   📅 Еженедельные задания:")
                for quest_info in weekly_quests:
                    status = "✅ Завершено" if quest_info['completed'] else "🔄 В процессе"
                    if quest_info['claimed']:
                        status = "💰 Награда получена"
                    if quest_info['is_expired']:
                        status = "⏰ Истекло"
                    
                    time_str = "Истекло"
                    if not quest_info['is_expired']:
                        days = int(quest_info['time_left'].total_seconds() // 86400)
                        hours = int((quest_info['time_left'].total_seconds() % 86400) // 3600)
                        time_str = f"{days}д {hours}ч"
                    
                    print(f"      • {quest_info['title']}: {quest_info['progress']}/{quest_info['target']} - {status} (истекает через {time_str})")
            
            print()
        
        print("=" * 60)
        print("✅ Проверка завершена")
        
    except Exception as e:
        print(f"❌ Ошибка при проверке заданий: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_quests_final() 