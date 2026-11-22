#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для добавления локализации заданий
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.localization import Localization

def add_quests_localization():
    """Добавить локализацию для заданий"""
    db = SessionLocal()
    
    try:
        # Проверяем, есть ли уже локализация заданий
        existing = db.query(Localization).filter(
            Localization.identifier.like('quest_%')
        ).first()
        
        if existing:
            print("✅ Локализация заданий уже существует")
            return
        
        # Локализация для заданий
        quests_localization = [
            # Ежедневные задания
            ("quest_daily_first_win", "Первая победа дня", "First Win of the Day"),
            ("quest_daily_first_win_desc", "Победите в 1 матче", "Win 1 match"),
            ("quest_daily_winner", "Победитель дня", "Daily Winner"),
            ("quest_daily_winner_desc", "Победите в 5 матчах", "Win 5 matches"),
            ("quest_daily_active_player", "Активный игрок", "Active Player"),
            ("quest_daily_active_player_desc", "Сыграйте 3 матча", "Play 3 matches"),
            ("quest_daily_win_streak", "Серия побед", "Win Streak"),
            ("quest_daily_win_streak_desc", "Победите 3 раза подряд", "Win 3 times in a row"),
            
            # Еженедельные задания
            ("quest_weekly_winner", "Недельный победитель", "Weekly Winner"),
            ("quest_weekly_winner_desc", "Победите в 10 матчах", "Win 10 matches"),
            ("quest_weekly_master", "Мастер недели", "Weekly Master"),
            ("quest_weekly_master_desc", "Победите в 50 матчах", "Win 50 matches"),
            ("quest_weekly_player", "Недельный игрок", "Weekly Player"),
            ("quest_weekly_player_desc", "Сыграйте 25 матчей", "Play 25 matches"),
            ("quest_weekly_mastery_streak", "Серия мастерства", "Mastery Streak"),
            ("quest_weekly_mastery_streak_desc", "Победите 10 раз подряд", "Win 10 times in a row"),
            
            # Общие тексты для заданий
            ("quests_title", "Задания", "Quests"),
            ("quests_daily", "Ежедневные", "Daily"),
            ("quests_weekly", "Еженедельные", "Weekly"),
            ("quests_no_daily", "Нет ежедневных заданий", "No daily quests"),
            ("quests_no_daily_description", "Ежедневные задания появятся завтра", "Daily quests will appear tomorrow"),
            ("quests_no_weekly", "Нет еженедельных заданий", "No weekly quests"),
            ("quests_no_weekly_description", "Еженедельные задания появятся в следующую неделю", "Weekly quests will appear next week"),
            ("profile_tab_quests", "Задания", "Quests"),
            ("quest_claim_reward", "Получить награду", "Claim Reward"),
            ("quest_completed", "Завершено", "Completed"),
            ("quest_in_progress", "В процессе", "In Progress"),
            ("quest_expired", "Истекло", "Expired"),
        ]
        
        for key, ru_text, en_text in quests_localization:
            localization = Localization(
                identifier=key,
                ru=ru_text,
                eng=en_text,
                webpage="quests"
            )
            db.add(localization)
        
        db.commit()
        print(f"✅ Добавлено {len(quests_localization)} ключей локализации для заданий")
        
    except Exception as e:
        print(f"❌ Ошибка при добавлении локализации: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Добавление локализации для системы заданий...")
    add_quests_localization()
    print("✅ Готово!") 