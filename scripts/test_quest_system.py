#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для тестирования системы заданий
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from datetime import datetime
from app.database import SessionLocal
from app.models.quest import Quest, UserQuest, QuestType, QuestCategory
from app.models.user import User
from app.models.match import Match

def test_quest_system():
    """Тестирование системы заданий"""
    db = SessionLocal()
    
    try:
        print("🔍 Тестирование системы заданий...")
        
        # Проверяем игрока Zira_aa
        user = db.query(User).filter(User.username == 'Zira_aa').first()
        if not user:
            print("❌ Пользователь Zira_aa не найден")
            return
        
        print(f"👤 Пользователь: {user.username}")
        print(f"💰 Баланс: {user.balance} монет")
        print(f"📊 Опыт: {user.experience}")
        print(f"⭐ Уровень: {user.level}")
        
        # Проверяем матчи за сегодня
        today = datetime.utcnow().date()
        today_matches = db.query(Match).filter(
            and_(
                (Match.winner_player == user.username) | (Match.loser_player == user.username),
                func.date(Match.match_date) == today
            )
        ).order_by(Match.match_date).all()
        
        print(f"\n🎮 Матчи за сегодня: {len(today_matches)}")
        total_matches = len(today_matches)
        wins = sum(1 for match in today_matches if match.winner_player == user.username)
        print(f"🏆 Победы: {wins}")
        print(f"💔 Поражения: {total_matches - wins}")
        
        # Проверяем задания
        user_quests = db.query(UserQuest).filter(
            and_(
                UserQuest.user_id == user.id,
                UserQuest.expires_at > datetime.utcnow()
            )
        ).all()
        
        print(f"\n📋 Активные задания: {len(user_quests)}")
        
        daily_completed = 0
        weekly_completed = 0
        
        for user_quest in user_quests:
            quest = user_quest.quest
            status = "✅ Завершено" if user_quest.is_completed else "🔄 В процессе"
            quest_type = "Ежедневное" if quest.quest_type == QuestType.DAILY else "Еженедельное"
            
            print(f"  - {quest.title_key}: {user_quest.current_progress}/{quest.target_value} ({status}) [{quest_type}]")
            
            if user_quest.is_completed:
                if quest.quest_type == QuestType.DAILY:
                    daily_completed += 1
                else:
                    weekly_completed += 1
        
        print(f"\n📈 Статистика выполнения:")
        print(f"  - Ежедневные: {daily_completed} выполнено")
        print(f"  - Еженедельные: {weekly_completed} выполнено")
        
        # Проверяем, какие задания должны быть выполнены
        print(f"\n🎯 Ожидаемые выполнения:")
        
        if wins >= 1:
            print(f"  ✅ Первая победа дня (1 победа) - выполнено")
        else:
            print(f"  ❌ Первая победа дня (1 победа) - не выполнено")
        
        if wins >= 5:
            print(f"  ✅ Победитель дня (5 побед) - выполнено")
        else:
            print(f"  ❌ Победитель дня (5 побед) - не выполнено ({wins}/5)")
        
        if total_matches >= 3:
            print(f"  ✅ Активный игрок (3 матча) - выполнено")
        else:
            print(f"  ❌ Активный игрок (3 матча) - не выполнено ({total_matches}/3)")
        
        # Проверяем серию побед
        current_streak = 0
        max_streak = 0
        for match in today_matches:
            if match.winner_player == user.username:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        
        if max_streak >= 3:
            print(f"  ✅ Серия побед (3 подряд) - выполнено")
        else:
            print(f"  ❌ Серия побед (3 подряд) - не выполнено (максимум: {max_streak})")
        
        print(f"\n✅ Тестирование завершено!")
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    test_quest_system() 