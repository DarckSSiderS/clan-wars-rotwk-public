#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Добавление локализованных названий фракций
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.localization import Localization

# Данные локализации для фракций
FACTION_LOCALIZATION_DATA = [
    {
        'identifier': 'faction_gondor',
        'ru': 'Гондор',
        'eng': 'Gondor',
        'webpage': 'common'
    },
    {
        'identifier': 'faction_rohan',
        'ru': 'Рохан',
        'eng': 'Rohan',
        'webpage': 'common'
    },
    {
        'identifier': 'faction_isengard',
        'ru': 'Изенгард',
        'eng': 'Isengard',
        'webpage': 'common'
    },
    {
        'identifier': 'faction_mordor',
        'ru': 'Мордор',
        'eng': 'Mordor',
        'webpage': 'common'
    },
    {
        'identifier': 'faction_angmar',
        'ru': 'Ангмар',
        'eng': 'Angmar',
        'webpage': 'common'
    },
    {
        'identifier': 'faction_misty_mountains',
        'ru': 'Мглистые Горы',
        'eng': 'Misty Mountains',
        'webpage': 'common'
    },
    {
        'identifier': 'faction_lothlorien',
        'ru': 'Лотлориэн',
        'eng': 'Lothlórien',
        'webpage': 'common'
    },
    {
        'identifier': 'faction_imladris',
        'ru': 'Имладрис',
        'eng': 'Imladris',
        'webpage': 'common'
    },
    {
        'identifier': 'faction_arnor',
        'ru': 'Арнор',
        'eng': 'Arnor',
        'webpage': 'common'
    },
    {
        'identifier': 'faction_harad',
        'ru': 'Харад',
        'eng': 'Harad',
        'webpage': 'common'
    },
    {
        'identifier': 'faction_dwarves',
        'ru': 'Гномы',
        'eng': 'Dwarves',
        'webpage': 'common'
    }
]

def add_faction_localization_data():
    """Добавляет локализационные данные для фракций"""
    print("Добавление локализационных данных для фракций...")
    
    db = SessionLocal()
    
    try:
        added_count = 0
        skipped_count = 0
        
        for data in FACTION_LOCALIZATION_DATA:
            # Проверяем, существует ли уже запись
            existing = db.query(Localization).filter(
                Localization.identifier == data['identifier'],
                Localization.webpage == data['webpage']
            ).first()
            
            if existing:
                print(f"Пропускаем существующую запись: {data['identifier']}")
                skipped_count += 1
            else:
                # Добавляем новую запись
                localization = Localization(
                    identifier=data['identifier'],
                    ru=data['ru'],
                    eng=data['eng'],
                    webpage=data['webpage']
                )
                db.add(localization)
                print(f"Добавлена запись: {data['identifier']}")
                added_count += 1
        
        # Подтверждаем изменения
        db.commit()
        
        print(f"Результат:")
        print(f"✅ Добавлено записей: {added_count}")
        print(f"⏭️  Пропущено существующих: {skipped_count}")
        print(f"📊 Всего обработано: {added_count + skipped_count}")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == '__main__':
    add_faction_localization_data() 