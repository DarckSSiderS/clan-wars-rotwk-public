import os
import sys
from dotenv import load_dotenv

# Добавляем путь к приложению
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from app.database import engine
from app.models.user import User
from app.models.role import Role

def make_user_admin(username: str):
    """Назначает роль администратора пользователю"""
    with Session(engine) as db:
        # Находим пользователя
        user = db.query(User).filter(User.username == username).first()
        if not user:
            print(f"❌ Пользователь '{username}' не найден")
            return
        
        # Находим роль администратора
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        if not admin_role:
            print("❌ Роль 'admin' не найдена в базе данных")
            return
        
        # Проверяем текущую роль
        if user.role and user.role.name == "admin":
            print(f"ℹ️ Пользователь '{username}' уже является администратором")
            return
        
        # Назначаем роль администратора
        user.role_id = admin_role.id
        db.commit()
        
        print(f"✅ Пользователь '{username}' успешно назначен администратором!")

if __name__ == "__main__":
    load_dotenv()
    
    if len(sys.argv) != 2:
        print("Использование: python make_admin.py <username>")
        print("Пример: python make_admin.py admin")
        sys.exit(1)
    
    username = sys.argv[1]
    make_user_admin(username) 