#!/usr/bin/env python3
"""
Скрипт для добавления ключей локализации для вкладок магазина
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.localization import Localization
from app.repositories.localization_repository import LocalizationRepository

def add_shop_tabs_localization():
    """Добавляет ключи локализации для вкладок магазина"""
    
    db = SessionLocal()
    repo = LocalizationRepository(db)
    
    # Ключи локализации для вкладок магазина
    shop_tabs_keys = [
        {
            "identifier": "shop_tab_available",
            "ru": "Доступные",
            "eng": "Available",
            "webpage": "shop"
        },
        {
            "identifier": "shop_tab_my_items",
            "ru": "Мои предметы", 
            "eng": "My Items",
            "webpage": "shop"
        }
    ]
    
    try:
        for item in shop_tabs_keys:
            # Проверяем, существует ли уже такой ключ
            existing = repo.get_by_identifier(item["identifier"])
            
            if existing:
                print(f"✅ Ключ '{item['identifier']}' уже существует")
            else:
                # Создаем новую запись локализации
                repo.create(
                    identifier=item["identifier"],
                    ru=item["ru"],
                    eng=item["eng"],
                    webpage=item["webpage"]
                )
                print(f"✅ Добавлен ключ '{item['identifier']}': '{item['ru']}' / '{item['eng']}'")
        
        db.commit()
        print("\n🎉 Локализация для вкладок магазина успешно добавлена!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка при добавлении локализации: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Добавление локализации для вкладок магазина...")
    add_shop_tabs_localization() 