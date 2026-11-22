#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для проверки результатов обновления имен игроков
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import datetime
from app.database import SessionLocal
from app.models.match import Match
from app.models.user import User
import re

def check_updated_matches():
    """Проверить результаты обновления имен игроков"""
    db = SessionLocal()
    
    try:
        print("🔍 Проверяем результаты обновления имен игроков...")
        print("=" * 80)
        
        # Подсчитываем общее количество матчей
        total_matches = db.query(Match).count()
        print(f"📊 Всего матчей в базе: {total_matches}")
        
        # Подсчитываем матчи с UUID (которые не были обновлены)
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
        
        matches_with_uuid = 0
        matches_with_names = 0
        
        # Получаем все матчи
        matches = db.query(Match).all()
        
        for match in matches:
            winner_is_uuid = bool(uuid_pattern.match(match.winner_player)) if match.winner_player else False
            loser_is_uuid = bool(uuid_pattern.match(match.loser_player)) if match.loser_player else False
            
            if winner_is_uuid or loser_is_uuid:
                matches_with_uuid += 1
            else:
                matches_with_names += 1
        
        print(f"✅ Матчей с именами игроков: {matches_with_names}")
        print(f"❌ Матчей с UUID (не обновлены): {matches_with_uuid}")
        
        if matches_with_uuid > 0:
            print(f"\n⚠️  Найдено {matches_with_uuid} матчей с UUID, которые не были обновлены")
            
            # Показываем примеры матчей с UUID
            print("\nПримеры матчей с UUID:")
            count = 0
            for match in matches:
                if count >= 5:  # Показываем только первые 5
                    break
                    
                winner_is_uuid = bool(uuid_pattern.match(match.winner_player)) if match.winner_player else False
                loser_is_uuid = bool(uuid_pattern.match(match.loser_player)) if match.loser_player else False
                
                if winner_is_uuid or loser_is_uuid:
                    print(f"  • {match.winner_player} vs {match.loser_player} ({match.match_date})")
                    count += 1
        
        # Показываем примеры успешно обновленных матчей
        print(f"\n✅ Примеры успешно обновленных матчей:")
        count = 0
        for match in matches:
            if count >= 10:  # Показываем только первые 10
                break
                
            winner_is_uuid = bool(uuid_pattern.match(match.winner_player)) if match.winner_player else False
            loser_is_uuid = bool(uuid_pattern.match(match.loser_player)) if match.loser_player else False
            
            if not winner_is_uuid and not loser_is_uuid:
                print(f"  • {match.winner_player} vs {match.loser_player} ({match.match_date})")
                count += 1
        
        # Статистика по игрокам
        print(f"\n📈 Статистика по игрокам:")
        
        # Получаем всех уникальных игроков
        all_players = set()
        for match in matches:
            if match.winner_player:
                all_players.add(match.winner_player)
            if match.loser_player:
                all_players.add(match.loser_player)
        
        players_with_uuid = [p for p in all_players if uuid_pattern.match(p)]
        players_with_names = [p for p in all_players if not uuid_pattern.match(p)]
        
        print(f"  Всего уникальных игроков: {len(all_players)}")
        print(f"  Игроков с именами: {len(players_with_names)}")
        print(f"  Игроков с UUID: {len(players_with_uuid)}")
        
        if players_with_names:
            print(f"\n🎮 Примеры игроков с именами:")
            for i, player in enumerate(players_with_names[:20]):
                print(f"  {i+1:2d}. {player}")
            if len(players_with_names) > 20:
                print(f"  ... и еще {len(players_with_names) - 20} игроков")
        
        if players_with_uuid:
            print(f"\n⚠️  Примеры игроков с UUID (не обновлены):")
            for i, player in enumerate(players_with_uuid[:10]):
                print(f"  {i+1:2d}. {player}")
            if len(players_with_uuid) > 10:
                print(f"  ... и еще {len(players_with_uuid) - 10} игроков")
        
        # Процент успешного обновления
        if total_matches > 0:
            success_rate = (matches_with_names / total_matches) * 100
            print(f"\n📊 Процент успешного обновления: {success_rate:.1f}%")
            
            if success_rate >= 90:
                print("🎉 Отличный результат! Большинство матчей успешно обновлены.")
            elif success_rate >= 70:
                print("✅ Хороший результат! Большинство матчей обновлены.")
            else:
                print("⚠️  Много матчей остались с UUID. Возможно, нужно добавить больше игроков в ладдер.")
        
    except Exception as e:
        print(f"❌ Ошибка при проверке: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_updated_matches() 