#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для сброса прогресса заданий Alotes1
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.database import SessionLocal
from app.models.quest import UserQuest
from app.models.user import User

def reset_alotes1_progress():
    print("=== Сброс прогресса заданий Alotes1 ===\n")
    
    db = SessionLocal()
    
    try:
        # Находим пользователя
        user = db.query(User).filter(User.username == 'Alotes1').first()
        if not user:
            print("❌ Пользователь Alotes1 не найден!")
            return
        
        print(f"✅ Пользователь найден: {user.username} (ID: {user.id})")
        
        # Сбрасываем прогресс всех заданий
        user_quests = db.query(UserQuest).filter(UserQuest.user_id == user.id).all()
        
        for user_quest in user_quests:
            old_progress = user_quest.current_progress
            user_quest.current_progress = 0
            print(f"  🔄 {user_quest.quest.title_key}: {old_progress} → 0")
        
        db.commit()
        print(f"\n✅ Прогресс сброшен для {len(user_quests)} заданий")
    
    finally:
        db.close()

if __name__ == '__main__':
    reset_alotes1_progress() 