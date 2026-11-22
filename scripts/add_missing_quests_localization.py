#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Добавление недостающих локализованных строк для квестов
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.localization import Localization

# Недостающие данные локализации для квестов
MISSING_QUESTS_LOCALIZATION_DATA = [
    {
        'identifier': 'quests_daily',
        'ru': 'Ежедневные',
        'eng': 'Daily',
        'webpage': 'quests'
    },
    {
        'identifier': 'quests_weekly',
        'ru': 'Еженедельные',
        'eng': 'Weekly',
        'webpage': 'quests'
    },
    {
        'identifier': 'quests_no_daily',
        'ru': 'Нет ежедневных заданий',
        'eng': 'No daily quests',
        'webpage': 'quests'
    },
    {
        'identifier': 'quests_no_daily_description',
        'ru': 'Ежедневные задания появятся завтра',
        'eng': 'Daily quests will appear tomorrow',
        'webpage': 'quests'
    },
    {
        'identifier': 'quests_no_weekly',
        'ru': 'Нет еженедельных заданий',
        'eng': 'No weekly quests',
        'webpage': 'quests'
    },
    {
        'identifier': 'quests_no_weekly_description',
        'ru': 'Еженедельные задания появятся в следующую неделю',
        'eng': 'Weekly quests will appear next week',
        'webpage': 'quests'
    },
    {
        'identifier': 'quest_claim_reward',
        'ru': 'Получить награду',
        'eng': 'Claim Reward',
        'webpage': 'quests'
    },
    {
        'identifier': 'quest_completed',
        'ru': 'Завершено',
        'eng': 'Completed',
        'webpage': 'quests'
    },
    {
        'identifier': 'quest_in_progress',
        'ru': 'В процессе',
        'eng': 'In Progress',
        'webpage': 'quests'
    },
    {
        'identifier': 'quest_expired',
        'ru': 'Истекло',
        'eng': 'Expired',
        'webpage': 'quests'
    }
]

def add_missing_quests_localization_data():
    """Добавляет недостающие локализационные данные для квестов"""
    print("Добавление недостающих локализационных данных для квестов...")
    
    db = SessionLocal()
    
    try:
        added_count = 0
        skipped_count = 0
        
        for data in MISSING_QUESTS_LOCALIZATION_DATA:
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
    add_missing_quests_localization_data() 