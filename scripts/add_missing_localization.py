#!/usr/bin/env python3
"""
Скрипт для добавления недостающих ключей локализации
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.localization import Localization

def add_missing_localization():
    """Добавляет недостающие ключи локализации"""
    db = SessionLocal()
    try:
        print("🔧 Добавление недостающих ключей локализации...")
        
        # Данные для локализации
        missing_data = [
            # Подзаголовки страниц
            {"webpage": "statistics", "identifier": "statistics_subtitle", "ru": "Аналитика и статистика игрового мира", "eng": "Game world analytics and statistics"},
            {"webpage": "clan-statistics", "identifier": "clan_statistics_subtitle", "ru": "Рейтинг и аналитика кланов", "eng": "Clan ranking and analytics"},
            {"webpage": "all-matches", "identifier": "all_matches_subtitle", "ru": "История всех игровых матчей", "eng": "History of all game matches"},
        ]
        
        added_count = 0
        updated_count = 0
        
        for item in missing_data:
            # Проверяем, существует ли уже запись
            existing = db.query(Localization).filter(
                Localization.webpage == item["webpage"],
                Localization.identifier == item["identifier"]
            ).first()
            
            if existing:
                # Обновляем существующую запись
                existing.ru = item["ru"]
                existing.eng = item["eng"]
                updated_count += 1
                print(f"  🔄 Обновлена: {item['webpage']}.{item['identifier']}")
            else:
                # Создаем новую запись
                new_localization = Localization(
                    webpage=item["webpage"],
                    identifier=item["identifier"],
                    ru=item["ru"],
                    eng=item["eng"]
                )
                db.add(new_localization)
                added_count += 1
                print(f"  ➕ Добавлена: {item['webpage']}.{item['identifier']}")
        
        db.commit()
        print(f"\n✅ Недостающие ключи локализации добавлены успешно!")
        print(f"  ➕ Добавлено записей: {added_count}")
        print(f"  🔄 Обновлено записей: {updated_count}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка при добавлении недостающих ключей локализации: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    add_missing_localization() 