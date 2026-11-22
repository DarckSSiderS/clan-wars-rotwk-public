#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для проверки локализации фракции "Гномы"
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models.localization import Localization

def check_dwarves_localization():
    """Проверить локализацию фракции 'Гномы'"""
    db = SessionLocal()
    
    try:
        print("🔍 Проверяем локализацию фракции 'Гномы'...")
        print("=" * 50)
        
        # Ищем локализацию для faction_dwarves
        texts = db.query(Localization).filter(Localization.identifier == 'faction_dwarves').all()
        
        if texts:
            print(f"✅ Найдено {len(texts)} записей локализации:")
            for text in texts:
                print(f"  {text.language}: {text.text}")
        else:
            print("❌ Локализация для 'faction_dwarves' не найдена")
            
            # Проверяем, есть ли другие фракции
            faction_texts = db.query(Localization).filter(
                Localization.identifier.like('faction_%')
            ).all()
            
            if faction_texts:
                print(f"\n📋 Найдено {len(faction_texts)} других фракций:")
                for text in faction_texts:
                    print(f"  {text.identifier}: {text.language} - {text.text}")
            else:
                print("❌ Вообще нет локализации фракций")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_dwarves_localization() 