#!/usr/bin/env python3
from database import SessionLocal
from models import UserItem, User, ShopItem

def fix_background():
    db = SessionLocal()
    try:
        # Находим пользователя
        user = db.query(User).filter(User.username == 'sadas').first()
        if not user:
            print("Пользователь не найден")
            return
            
        # Отключаем все фоны этого пользователя
        bg_items = db.query(UserItem).join(ShopItem).filter(
            UserItem.user_id == user.id,
            ShopItem.item_type == 'profile_background'
        ).all()
        
        for item in bg_items:
            item.is_equipped = False
            
        # Включаем только космический фон
        space_bg = db.query(UserItem).filter(
            UserItem.user_id == user.id,
            UserItem.item_id == 8
        ).first()
        
        if space_bg:
            space_bg.is_equipped = True
            print("Космический фон активирован")
        else:
            print("Космический фон не найден у пользователя")
            
        db.commit()
        
    except Exception as e:
        print(f"Ошибка: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_background()