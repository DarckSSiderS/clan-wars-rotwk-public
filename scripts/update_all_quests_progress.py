#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для обновления прогресса заданий всех пользователей
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from datetime import datetime, timedelta
import pytz
from app.database import SessionLocal
from app.models.quest import Quest, UserQuest, QuestType, QuestCategory
from app.models.user import User
from app.models.match import Match

def update_all_quests_progress():
    print("=== Обновление прогресса заданий всех пользователей ===\n")
    
    db = SessionLocal()
    
    try:
        # Получаем всех пользователей
        users = db.query(User).all()
        print(f"Найдено пользователей: {len(users)}")
        
        # Настройка времени (МСК)
        moscow_tz = pytz.timezone('Europe/Moscow')
        today_moscow = datetime.now(moscow_tz).date()
        today_start = datetime.combine(today_moscow, datetime.min.time())
        today_start = moscow_tz.localize(today_start)
        today_end = today_start + timedelta(days=1)
        
        # Начало недели для еженедельных заданий
        week_start = today_start - timedelta(days=today_start.weekday())
        
        updated_count = 0
        
        for user in users:
            print(f"\n👤 Обрабатываем пользователя: {user.username}")
            
            # Получаем активные задания пользователя
            user_quests = db.query(UserQuest).filter(
                and_(
                    UserQuest.user_id == user.id,
                    UserQuest.expires_at > datetime.utcnow(),
                    UserQuest.is_claimed == False
                )
            ).all()
            
            if not user_quests:
                print(f"  ⚠️  Нет активных заданий")
                continue
            
            # Статистика за сегодня
            today_wins = db.query(Match).filter(
                and_(
                    Match.winner_player == user.username,
                    Match.match_date >= today_start,
                    Match.match_date < today_end
                )
            ).count()
            
            today_losses = db.query(Match).filter(
                and_(
                    Match.loser_player == user.username,
                    Match.match_date >= today_start,
                    Match.match_date < today_end
                )
            ).count()
            
            today_total = today_wins + today_losses
            
            # Статистика за неделю
            week_wins = db.query(Match).filter(
                and_(
                    Match.winner_player == user.username,
                    Match.match_date >= week_start,
                    Match.match_date < today_end
                )
            ).count()
            
            week_losses = db.query(Match).filter(
                and_(
                    Match.loser_player == user.username,
                    Match.match_date >= week_start,
                    Match.match_date < today_end
                )
            ).count()
            
            week_total = week_wins + week_losses
            
            print(f"  📊 Сегодня: {today_wins} побед, {today_losses} поражений (всего {today_total})")
            print(f"  📊 За неделю: {week_wins} побед, {week_losses} поражений (всего {week_total})")
            
            # Обновляем каждое задание
            for user_quest in user_quests:
                quest = user_quest.quest
                old_progress = user_quest.current_progress
                updated = False
                
                if quest.quest_type == QuestType.DAILY:
                    if quest.category == QuestCategory.WINS:
                        if user_quest.current_progress != today_wins:
                            user_quest.current_progress = today_wins
                            updated = True
                    elif quest.category == QuestCategory.MATCHES_PLAYED:
                        if user_quest.current_progress != today_total:
                            user_quest.current_progress = today_total
                            updated = True
                    elif quest.category == QuestCategory.STREAK:
                        # Для серии побед считаем максимальную серию за сегодня
                        today_matches = db.query(Match).filter(
                            and_(
                                (Match.winner_player == user.username) | (Match.loser_player == user.username),
                                Match.match_date >= today_start,
                                Match.match_date < today_end
                            )
                        ).order_by(Match.match_date).all()
                        
                        current_streak = 0
                        max_streak = 0
                        for match in today_matches:
                            if match.winner_player == user.username:
                                current_streak += 1
                                max_streak = max(max_streak, current_streak)
                            else:
                                current_streak = 0
                        
                        if user_quest.current_progress != max_streak:
                            user_quest.current_progress = max_streak
                            updated = True
                
                elif quest.quest_type == QuestType.WEEKLY:
                    if quest.category == QuestCategory.WINS:
                        if user_quest.current_progress != week_wins:
                            user_quest.current_progress = week_wins
                            updated = True
                    elif quest.category == QuestCategory.MATCHES_PLAYED:
                        if user_quest.current_progress != week_total:
                            user_quest.current_progress = week_total
                            updated = True
                    elif quest.category == QuestCategory.STREAK:
                        # Для серии побед считаем максимальную серию за неделю
                        week_matches = db.query(Match).filter(
                            and_(
                                (Match.winner_player == user.username) | (Match.loser_player == user.username),
                                Match.match_date >= week_start,
                                Match.match_date < today_end
                            )
                        ).order_by(Match.match_date).all()
                        
                        current_streak = 0
                        max_streak = 0
                        for match in week_matches:
                            if match.winner_player == user.username:
                                current_streak += 1
                                max_streak = max(max_streak, current_streak)
                            else:
                                current_streak = 0
                        
                        if user_quest.current_progress != max_streak:
                            user_quest.current_progress = max_streak
                            updated = True
                
                if updated:
                    print(f"  ✅ {quest.title_key}: {old_progress} → {user_quest.current_progress}/{quest.target_value}")
                    updated_count += 1
                
                # Проверяем, завершено ли задание (независимо от updated)
                if user_quest.current_progress >= quest.target_value and not user_quest.is_completed:
                    user_quest.is_completed = True
                    user_quest.completed_at = datetime.utcnow()
                    print(f"  🎉 Задание {quest.title_key} ЗАВЕРШЕНО!")
                    updated_count += 1
        
        # Сохраняем изменения
        if updated_count > 0:
            db.commit()
            print(f"\n✅ Обновлено {updated_count} заданий")
        else:
            print(f"\nℹ️  Нет заданий для обновления")
    
    finally:
        db.close()

if __name__ == '__main__':
    update_all_quests_progress() 