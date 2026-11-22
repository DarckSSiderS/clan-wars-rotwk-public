import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models.localization import Localization

def check_localization_encoding():
    db = SessionLocal()
    
    try:
        # Получаем все записи локализации
        localizations = db.query(Localization).all()
        
        print("=== Проверка кодировки данных локализации ===")
        for loc in localizations:
            print(f"\nИдентификатор: {loc.identifier}")
            print(f"RU: {repr(loc.ru)}")
            print(f"ENG: {repr(loc.eng)}")
            print(f"Webpage: {loc.webpage}")
            
            # Проверяем, что русский текст корректный
            if "Добро пожаловать" in loc.ru:
                print("✅ Русский текст корректный")
            else:
                print("❌ Русский текст некорректный")
                
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    # Устанавливаем переменную окружения для базы данных
    os.environ['DATABASE_URL'] = "postgresql://clanwar_user:clanwar_password@localhost:5432/clanwar_db"
    check_localization_encoding() 