#!/usr/bin/env python3
"""
Скрипт для добавления локализации для страницы матчей
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.localization import Localization

def add_matches_localization():
    """Добавляет локализацию для страницы матчей"""
    db = SessionLocal()
    try:
        print("🔧 Добавление локализации для страницы матчей...")
        
        # Данные для локализации
        localization_data = [
            {"webpage": "all-matches", "identifier": "all_matches_faction_winner", "ru": "Фракция (Победитель)", "eng": "Faction (Winner)"},
            {"webpage": "all-matches", "identifier": "all_matches_faction_loser", "ru": "Фракция (Проигравший)", "eng": "Faction (Loser)"},
        ]
        
        added_count = 0
        updated_count = 0
        
        for item in localization_data:
            try:
                # Проверяем, существует ли уже запись
                existing = db.query(Localization).filter(
                    Localization.webpage == item["webpage"],
                    Localization.identifier == item["identifier"]
                ).first()
                
                if existing:
                    # Обновляем существующую запись
                    existing.ru = item["ru"]
                    existing.eng = item["eng"]
                    db.commit()
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
                    db.commit()
                    added_count += 1
                    print(f"  ➕ Добавлена: {item['webpage']}.{item['identifier']}")
                    
            except Exception as e:
                db.rollback()
                print(f"  ❌ Ошибка при обработке {item['identifier']}: {e}")
                continue
        
        print(f"\n✅ Локализация для страницы матчей добавлена успешно!")
        print(f"  ➕ Добавлено записей: {added_count}")
        print(f"  🔄 Обновлено записей: {updated_count}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка при добавлении локализации: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    add_matches_localization() 