import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.user import User
from app.services.quest_service import QuestService

def fix_user_levels():
    """Исправить уровни всех пользователей на основе их опыта"""
    
    db = SessionLocal()
    quest_service = QuestService()
    
    try:
        # Получаем всех пользователей
        users = db.query(User).all()
        
        print(f"🔍 Найдено {len(users)} пользователей")
        
        updated_count = 0
        
        for user in users:
            # Рассчитываем правильный уровень на основе опыта
            correct_level = quest_service.calculate_level_from_experience(user.experience)
            
            # Если уровень неправильный, обновляем его
            if user.level != correct_level:
                old_level = user.level
                user.level = correct_level
                updated_count += 1
                
                print(f"👤 {user.username}: уровень {old_level} -> {correct_level} (опыт: {user.experience})")
        
        if updated_count > 0:
            db.commit()
            print(f"\n✅ Обновлено {updated_count} пользователей")
        else:
            print("\n✅ Все уровни уже правильные")
            
        # Показываем статистику
        print("\n📊 Статистика уровней:")
        level_stats = {}
        for user in users:
            level = user.level
            if level not in level_stats:
                level_stats[level] = 0
            level_stats[level] += 1
        
        for level in sorted(level_stats.keys()):
            count = level_stats[level]
            print(f"Уровень {level}: {count} пользователей")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_user_levels() 