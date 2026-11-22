#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка статуса is_completed заданий
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.database import SessionLocal
from app.models.quest import UserQuest
from app.models.user import User

def check_completed_status():
    print("=== Проверка статуса is_completed заданий ===\n")
    
    db = SessionLocal()
    
    try:
        # Находим пользователя
        user = db.query(User).filter(User.username == 'Alotes1').first()
        if not user:
            print("❌ Пользователь Alotes1 не найден!")
            return
        
        print(f"✅ Пользователь найден: {user.username} (ID: {user.id})")
        
        # Получаем все задания пользователя
        user_quests = db.query(UserQuest).filter(UserQuest.user_id == user.id).all()
        
        print(f"\n📋 Задания Alotes1:")
        for user_quest in user_quests:
            quest = user_quest.quest
            is_completed = user_quest.current_progress >= quest.target_value
            
            print(f"\n🎯 {quest.title_key} ({quest.quest_type})")
            print(f"   📈 Прогресс: {user_quest.current_progress}/{quest.target_value}")
            print(f"   ✅ is_completed в БД: {user_quest.is_completed}")
            print(f"   🎯 Должно быть completed: {is_completed}")
            print(f"   ⏰ completed_at: {user_quest.completed_at}")
            
            if user_quest.is_completed != is_completed:
                print(f"   ⚠️  НЕСООТВЕТСТВИЕ! is_completed должен быть {is_completed}")
    
    finally:
        db.close()

if __name__ == '__main__':
    check_completed_status() 