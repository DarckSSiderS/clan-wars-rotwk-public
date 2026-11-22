import os
import sys
from dotenv import load_dotenv

# Добавляем путь к приложению
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from app.database import engine, get_db
from app.models.role import Role

def init_roles():
    """Инициализация ролей в базе данных"""
    with Session(engine) as db:
        # Проверяем, существуют ли уже роли
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        user_role = db.query(Role).filter(Role.name == "user").first()
        contentmaker_role = db.query(Role).filter(Role.name == "contentmaker").first()
        
        if not admin_role:
            admin_role = Role(
                name="admin",
                description="Администратор системы"
            )
            db.add(admin_role)
            print("✅ Роль 'admin' создана")
        else:
            print("ℹ️ Роль 'admin' уже существует")
        
        if not user_role:
            user_role = Role(
                name="user", 
                description="Обычный пользователь"
            )
            db.add(user_role)
            print("✅ Роль 'user' создана")
        else:
            print("ℹ️ Роль 'user' уже существует")
        
        if not contentmaker_role:
            contentmaker_role = Role(
                name="contentmaker",
                description="Контентмейкер - пользователь с доступом к социальным сетям"
            )
            db.add(contentmaker_role)
            print("✅ Роль 'contentmaker' создана")
        else:
            print("ℹ️ Роль 'contentmaker' уже существует")
        
        db.commit()
        print("🎉 Инициализация ролей завершена!")

if __name__ == "__main__":
    load_dotenv()
    init_roles() 