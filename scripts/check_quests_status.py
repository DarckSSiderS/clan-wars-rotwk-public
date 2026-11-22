#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для проверки статуса заданий пользователей
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime
from app.database import SessionLocal
from app.models.quest import UserQuest, Quest, QuestType
from app.models.user import User

def check_user_quests(username: str = None):
    """Проверить задания пользователя или всех пользователей"""
    db = SessionLocal()
    
    try:
        now = datetime.utcnow()
        print(f"🕐 Текущее время (UTC): {now}")
        print(f"🕐 Текущее время (Москва): {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        if username:
            # Проверяем конкретного пользователя
            user = db.query(User).filter(User.username == username).first()
            if not user:
                print(f"❌ Пользователь {username} не найден")
                return
            
            users = [user]
        else:
            # Проверяем всех пользователей с заданиями
            users = db.query(User).join(UserQuest).distinct().all()
        
        for user in users:
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
                is_expired = expires_at_utc <= now
                time_left = expires_at_utc - now
                
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
                for quest in daily_quests:
                    status = "✅ Завершено" if quest['completed'] else "🔄 В процессе"
                    if quest['claimed']:
                        status = "💰 Награда получена"
                    elif quest['is_expired']:
                        status = "⏰ Истекло"
                    
                    time_str = f"Истекло {abs(quest['time_left']).days}д {abs(quest['time_left']).seconds//3600}ч назад" if quest['is_expired'] else f"Осталось {quest['time_left'].days}д {quest['time_left'].seconds//3600}ч"
                    
                    print(f"      • {quest['title']}: {quest['progress']}/{quest['target']} - {status}")
                    print(f"        Время: {time_str}")
            
            # Выводим еженедельные задания
            if weekly_quests:
                print("   📅 Еженедельные задания:")
                for quest in weekly_quests:
                    status = "✅ Завершено" if quest['completed'] else "🔄 В процессе"
                    if quest['claimed']:
                        status = "💰 Награда получена"
                    elif quest['is_expired']:
                        status = "⏰ Истекло"
                    
                    time_str = f"Истекло {abs(quest['time_left']).days}д {abs(quest['time_left']).seconds//3600}ч назад" if quest['is_expired'] else f"Осталось {quest['time_left'].days}д {quest['time_left'].seconds//3600}ч"
                    
                    print(f"      • {quest['title']}: {quest['progress']}/{quest['target']} - {status}")
                    print(f"        Время: {time_str}")
            
            print()
    
    except Exception as e:
        print(f"❌ Ошибка при проверке заданий: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        username = sys.argv[1]
        print(f"🔍 Проверка заданий пользователя: {username}")
        check_user_quests(username)
    else:
        print("🔍 Проверка заданий всех пользователей")
        check_user_quests() 