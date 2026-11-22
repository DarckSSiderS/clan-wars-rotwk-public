#!/usr/bin/env python3
"""
Скрипт для добавления локализации фракций в базу данных
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.localization import Localization

def add_factions_localization():
    """Добавляет локализацию для фракций"""
    db = SessionLocal()
    try:
        print("🔧 Добавление локализации для фракций...")
        
        # Данные для локализации фракций
        factions_data = [
            {"webpage": "factions", "identifier": "faction_gondor", "ru": "Гондор", "eng": "Gondor"},
            {"webpage": "factions", "identifier": "faction_rohan", "ru": "Рохан", "eng": "Rohan"},
            {"webpage": "factions", "identifier": "faction_isengard", "ru": "Изенгард", "eng": "Isengard"},
            {"webpage": "factions", "identifier": "faction_mordor", "ru": "Мордор", "eng": "Mordor"},
            {"webpage": "factions", "identifier": "faction_angmar", "ru": "Ангмар", "eng": "Angmar"},
            {"webpage": "factions", "identifier": "faction_dwarves", "ru": "Гномы", "eng": "Dwarves"},
            {"webpage": "factions", "identifier": "faction_harad", "ru": "Харад", "eng": "Harad"},
            {"webpage": "factions", "identifier": "faction_arnor", "ru": "Арнор", "eng": "Arnor"},
            {"webpage": "factions", "identifier": "faction_lothlorien", "ru": "Лотлориэн", "eng": "Lothlórien"},
            {"webpage": "factions", "identifier": "faction_imladris", "ru": "Имладрис", "eng": "Imladris"},
            {"webpage": "factions", "identifier": "faction_misty_mountains", "ru": "Мглистые Горы", "eng": "Misty Mountains"},
        ]
        
        added_count = 0
        updated_count = 0
        
        for item in factions_data:
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
        print(f"\n✅ Локализация фракций добавлена успешно!")
        print(f"  ➕ Добавлено записей: {added_count}")
        print(f"  🔄 Обновлено записей: {updated_count}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка при добавлении локализации фракций: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    add_factions_localization() 