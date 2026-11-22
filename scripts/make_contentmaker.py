#!/usr/bin/env python3
"""
Скрипт для назначения роли contentmaker пользователю
"""

import os
import sys
from dotenv import load_dotenv

# Добавляем путь к приложению
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import engine
from app.models.user import User
from app.models.role import Role

def make_user_contentmaker(username: str):
    """Назначает роль contentmaker пользователю"""
    with Session(engine) as db:
        # Находим пользователя
        user = db.query(User).filter(User.username == username).first()
        if not user:
            print(f"❌ Пользователь '{username}' не найден")
            return
        
        # Находим роль contentmaker
        contentmaker_role = db.query(Role).filter(Role.name == "contentmaker").first()
        if not contentmaker_role:
            print("❌ Роль 'contentmaker' не найдена в базе данных")
            return
        
        # Проверяем текущую роль
        if user.role and user.role.name == "contentmaker":
            print(f"ℹ️ Пользователь '{username}' уже является контентмейкером")
            return
        
        # Назначаем роль contentmaker
        user.role_id = contentmaker_role.id
        db.commit()
        
        print(f"✅ Пользователь '{username}' успешно назначен контентмейкером!")
        print(f"📊 ID роли: {contentmaker_role.id}")
        print(f"📝 Описание роли: {contentmaker_role.description}")

if __name__ == "__main__":
    load_dotenv()
    
    # Имя пользователя для назначения роли
    username = "Фарамир"  # Можно изменить на другое имя
    
    print(f"🚀 Назначаем роль contentmaker пользователю '{username}'...")
    print("=" * 60)
    
    make_user_contentmaker(username) 