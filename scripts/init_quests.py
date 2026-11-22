#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для инициализации системы заданий
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.quest import Quest, QuestType, QuestCategory

def init_quests():
    """Инициализация заданий в базе данных"""
    db = SessionLocal()
    
    try:
        # Проверяем, есть ли уже задания
        existing_quests = db.query(Quest).count()
        if existing_quests > 0:
            print(f"✅ Задания уже существуют ({existing_quests} шт.)")
            return
        
        # Ежедневные задания
        daily_quests = [
            {
                "title_key": "quest_daily_first_win",
                "description_key": "quest_daily_first_win_desc",
                "quest_type": QuestType.DAILY,
                "category": QuestCategory.WINS,
                "target_value": 1,
                "reward_coins": 100,
                "reward_experience": 50
            },
            {
                "title_key": "quest_daily_winner",
                "description_key": "quest_daily_winner_desc",
                "quest_type": QuestType.DAILY,
                "category": QuestCategory.WINS,
                "target_value": 5,
                "reward_coins": 500,
                "reward_experience": 200
            },
            {
                "title_key": "quest_daily_active_player",
                "description_key": "quest_daily_active_player_desc",
                "quest_type": QuestType.DAILY,
                "category": QuestCategory.MATCHES_PLAYED,
                "target_value": 3,
                "reward_coins": 150,
                "reward_experience": 75
            },
            {
                "title_key": "quest_daily_win_streak",
                "description_key": "quest_daily_win_streak_desc",
                "quest_type": QuestType.DAILY,
                "category": QuestCategory.STREAK,
                "target_value": 3,
                "reward_coins": 300,
                "reward_experience": 150
            }
        ]
        
        # Еженедельные задания
        weekly_quests = [
            {
                "title_key": "quest_weekly_winner",
                "description_key": "quest_weekly_winner_desc",
                "quest_type": QuestType.WEEKLY,
                "category": QuestCategory.WINS,
                "target_value": 10,
                "reward_coins": 1000,
                "reward_experience": 500
            },
            {
                "title_key": "quest_weekly_master",
                "description_key": "quest_weekly_master_desc",
                "quest_type": QuestType.WEEKLY,
                "category": QuestCategory.WINS,
                "target_value": 50,
                "reward_coins": 3000,
                "reward_experience": 1500
            },
            {
                "title_key": "quest_weekly_player",
                "description_key": "quest_weekly_player_desc",
                "quest_type": QuestType.WEEKLY,
                "category": QuestCategory.MATCHES_PLAYED,
                "target_value": 25,
                "reward_coins": 800,
                "reward_experience": 400
            },
            {
                "title_key": "quest_weekly_mastery_streak",
                "description_key": "quest_weekly_mastery_streak_desc",
                "quest_type": QuestType.WEEKLY,
                "category": QuestCategory.STREAK,
                "target_value": 10,
                "reward_coins": 2000,
                "reward_experience": 1000
            }
        ]
        
        # Создаем все задания
        all_quests = daily_quests + weekly_quests
        
        for quest_data in all_quests:
            quest = Quest(**quest_data)
            db.add(quest)
        
        db.commit()
        print(f"✅ Создано {len(all_quests)} заданий:")
        print(f"   - Ежедневных: {len(daily_quests)}")
        print(f"   - Еженедельных: {len(weekly_quests)}")
        
    except Exception as e:
        print(f"❌ Ошибка при создании заданий: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Инициализация системы заданий...")
    init_quests()
    print("✅ Готово!") 