#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Простая проверка пользователя Alotes1
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

def check_alotes1():
    print("=== Проверка пользователя Alotes1 ===\n")
    
    db = SessionLocal()
    
    try:
        # Находим пользователя
        user = db.query(User).filter(User.username == 'Alotes1').first()
        if not user:
            print("❌ Пользователь Alotes1 не найден!")
            return
        
        print(f"✅ Пользователь найден: {user.username} (ID: {user.id})")
        print(f"💰 Баланс: {user.balance}, 📊 Уровень: {user.level}, ⭐ Опыт: {user.experience}")
        
        # Проверяем матчи за сегодня (МСК)
        moscow_tz = pytz.timezone('Europe/Moscow')
        today_moscow = datetime.now(moscow_tz).date()
        today_start = datetime.combine(today_moscow, datetime.min.time())
        today_start = moscow_tz.localize(today_start)
        today_end = today_start + timedelta(days=1)
        
        print(f"\n📅 Сегодня (МСК): {today_moscow}")
        print(f"⏰ Период проверки: {today_start} - {today_end}")
        
        # Матчи где Alotes1 был победителем
        wins = db.query(Match).filter(
            and_(
                Match.winner_player == 'Alotes1',
                Match.match_date >= today_start,
                Match.match_date < today_end
            )
        ).order_by(Match.match_date).all()
        
        # Матчи где Alotes1 был проигравшим
        losses = db.query(Match).filter(
            and_(
                Match.loser_player == 'Alotes1',
                Match.match_date >= today_start,
                Match.match_date < today_end
            )
        ).order_by(Match.match_date).all()
        
        print(f"\n🏆 Победы сегодня: {len(wins)}")
        for match in wins:
            print(f"  ✅ {match.winner_player} ({match.winner_faction}) vs {match.loser_player} ({match.loser_faction})")
            print(f"     📍 Карта: {match.map_name}, 📅 Дата: {match.match_date}")
        
        print(f"\n❌ Поражения сегодня: {len(losses)}")
        for match in losses:
            print(f"  ❌ {match.winner_player} ({match.winner_faction}) vs {match.loser_player} ({match.loser_faction})")
            print(f"     📍 Карта: {match.map_name}, 📅 Дата: {match.match_date}")
        
        total_matches_today = len(wins) + len(losses)
        print(f"\n📊 Всего матчей сегодня: {total_matches_today}")
        
        # Проверяем задания пользователя
        print(f"\n📋 Задания Alotes1:")
        user_quests = db.query(UserQuest).filter(UserQuest.user_id == user.id).all()
        
        if not user_quests:
            print("❌ У пользователя нет заданий!")
            return
        
        for user_quest in user_quests:
            quest = user_quest.quest
            print(f"\n🎯 {quest.title_key} ({quest.quest_type})")
            print(f"   📈 Прогресс: {user_quest.current_progress}/{quest.target_value}")
            print(f"   ✅ Получена награда: {user_quest.is_claimed}")
            print(f"   ⏰ Истекает: {user_quest.expires_at}")
            
            # Проверяем, должен ли прогресс обновиться
            if quest.quest_type == QuestType.DAILY:
                # Для ежедневных заданий считаем матчи за сегодня
                if quest.category == QuestCategory.WINS:
                    expected_progress = len(wins)
                elif quest.category == QuestCategory.MATCHES_PLAYED:
                    expected_progress = total_matches_today
                else:
                    expected_progress = 0
                    
                print(f"   🔍 Ожидаемый прогресс: {expected_progress}")
                if user_quest.current_progress != expected_progress:
                    print(f"   ⚠️  ПРОГРЕСС НЕ ОБНОВЛЕН! Должно быть {expected_progress}, а есть {user_quest.current_progress}")
            
            elif quest.quest_type == QuestType.WEEKLY:
                # Для еженедельных заданий считаем матчи за неделю
                week_start = today_start - timedelta(days=today_start.weekday())
                
                week_wins = db.query(Match).filter(
                    and_(
                        Match.winner_player == 'Alotes1',
                        Match.match_date >= week_start,
                        Match.match_date < today_end
                    )
                ).count()
                
                week_losses = db.query(Match).filter(
                    and_(
                        Match.loser_player == 'Alotes1',
                        Match.match_date >= week_start,
                        Match.match_date < today_end
                    )
                ).count()
                
                week_total = week_wins + week_losses
                
                if quest.category == QuestCategory.WINS:
                    expected_progress = week_wins
                elif quest.category == QuestCategory.MATCHES_PLAYED:
                    expected_progress = week_total
                else:
                    expected_progress = 0
                    
                print(f"   🔍 Ожидаемый прогресс за неделю: {expected_progress}")
                if user_quest.current_progress != expected_progress:
                    print(f"   ⚠️  ПРОГРЕСС НЕ ОБНОВЛЕН! Должно быть {expected_progress}, а есть {user_quest.current_progress}")
    
    finally:
        db.close()

if __name__ == '__main__':
    check_alotes1() 