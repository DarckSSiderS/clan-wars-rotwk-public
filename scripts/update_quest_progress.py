#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для обновления прогресса заданий на основе матчей
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models.quest import Quest, UserQuest, QuestType, QuestCategory
from app.models.user import User
from app.models.match import Match

def update_quest_progress_for_user(db: Session, user_id: int, username: str):
    """Обновить прогресс заданий для конкретного пользователя"""
    # Получаем активные задания пользователя
    user_quests = db.query(UserQuest).filter(
        and_(
            UserQuest.user_id == user_id,
            UserQuest.expires_at > datetime.utcnow(),
            UserQuest.is_completed == False
        )
    ).all()
    
    if not user_quests:
        print(f"У пользователя {username} нет активных заданий")
        return
    
    # Получаем статистику за сегодня
    today = datetime.utcnow().date()
    today_matches = db.query(Match).filter(
        and_(
            (Match.winner_player == username) | (Match.loser_player == username),
            func.date(Match.match_date) == today
        )
    ).order_by(Match.match_date).all()
    
    if not today_matches:
        print(f"У пользователя {username} нет матчей за сегодня")
        return
    
    # Подсчитываем статистику
    total_matches = len(today_matches)
    wins = sum(1 for match in today_matches if match.winner_player == username)
    
    print(f"Статистика {username} за сегодня: {wins} побед из {total_matches} матчей")
    
    # Обновляем прогресс для каждого задания
    for user_quest in user_quests:
        quest = user_quest.quest
        updated = False
        
        if quest.category == QuestCategory.WINS:
            if user_quest.current_progress != wins:
                user_quest.current_progress = wins
                updated = True
                print(f"  - {quest.title_key}: {wins}/{quest.target_value} побед")
        
        elif quest.category == QuestCategory.MATCHES_PLAYED:
            if user_quest.current_progress != total_matches:
                user_quest.current_progress = total_matches
                updated = True
                print(f"  - {quest.title_key}: {total_matches}/{quest.target_value} матчей")
        
        elif quest.category == QuestCategory.STREAK:
            # Для серии побед нужно посчитать максимальную серию
            current_streak = 0
            max_streak = 0
            for match in today_matches:
                if match.winner_player == username:
                    current_streak += 1
                    max_streak = max(max_streak, current_streak)
                else:
                    current_streak = 0
            
            if user_quest.current_progress != max_streak:
                user_quest.current_progress = max_streak
                updated = True
                print(f"  - {quest.title_key}: {max_streak}/{quest.target_value} подряд")
        
        # Проверяем, завершено ли задание
        if updated and user_quest.current_progress >= quest.target_value:
            user_quest.is_completed = True
            user_quest.completed_at = datetime.utcnow()
            print(f"  ✅ Задание {quest.title_key} ЗАВЕРШЕНО!")
            
            # Выдаем награды
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.balance += quest.reward_coins
                user.experience += quest.reward_experience
                print(f"  💰 Награда: +{quest.reward_coins} монет, +{quest.reward_experience} опыта")
    
    if updated:
        db.commit()
        print(f"✅ Прогресс заданий для {username} обновлен")
    else:
        print(f"ℹ️ Прогресс заданий для {username} не изменился")

def update_all_users_quest_progress():
    """Обновить прогресс заданий для всех пользователей"""
    db = SessionLocal()
    
    try:
        # Получаем всех пользователей с активными заданиями
        users_with_quests = db.query(User).join(UserQuest).filter(
            UserQuest.expires_at > datetime.utcnow()
        ).distinct().all()
        
        print(f"Найдено {len(users_with_quests)} пользователей с активными заданиями")
        
        for user in users_with_quests:
            update_quest_progress_for_user(db, user.id, user.username)
        
    except Exception as e:
        print(f"❌ Ошибка при обновлении прогресса: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Обновление прогресса заданий...")
    update_all_users_quest_progress()
    print("✅ Готово!") 