#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для добавления поля is_claimed в таблицу user_quests
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal

def add_claimed_field():
    """Добавить поле is_claimed в таблицу user_quests"""
    db = SessionLocal()
    
    try:
        # Проверяем, существует ли уже поле
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'user_quests' AND column_name = 'is_claimed'
        """))
        
        if result.fetchone():
            print("✅ Поле is_claimed уже существует")
            return
        
        # Добавляем поле
        db.execute(text("ALTER TABLE user_quests ADD COLUMN is_claimed BOOLEAN DEFAULT FALSE"))
        db.commit()
        print("✅ Поле is_claimed добавлено в таблицу user_quests")
        
    except Exception as e:
        print(f"❌ Ошибка при добавлении поля: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Добавление поля is_claimed...")
    add_claimed_field()
    print("✅ Готово!") 