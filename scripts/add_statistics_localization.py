#!/usr/bin/env python3
"""
Скрипт для добавления локализации страниц статистики в базу данных
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.localization import Localization
from datetime import datetime

def add_statistics_localization():
    """Добавляет локализацию для страниц статистики"""
    db = SessionLocal()
    try:
        print("🔧 Добавление локализации для страниц статистики...")
        
        # Данные для локализации
        localization_data = [
            # Навигация
            {"webpage": "navigation", "identifier": "nav_statistics", "ru": "Статистика", "en": "Statistics"},
            {"webpage": "navigation", "identifier": "nav_statistics_overall", "ru": "Общая статистика", "en": "Overall Statistics"},
            {"webpage": "navigation", "identifier": "nav_statistics_clans", "ru": "Статистика кланов", "en": "Clan Statistics"},
            {"webpage": "navigation", "identifier": "nav_statistics_matches", "ru": "Все матчи", "en": "All Matches"},
            
            # Общая статистика
            {"webpage": "statistics", "identifier": "statistics_title", "ru": "Общая статистика", "en": "Overall Statistics"},
            {"webpage": "statistics", "identifier": "statistics_total_matches", "ru": "Всего матчей", "en": "Total Matches"},
            {"webpage": "statistics", "identifier": "statistics_total_players", "ru": "Игроков", "en": "Players"},
            {"webpage": "statistics", "identifier": "statistics_total_clans", "ru": "Кланов", "en": "Clans"},
            {"webpage": "statistics", "identifier": "statistics_matches_today", "ru": "Матчей сегодня", "en": "Matches Today"},
            {"webpage": "statistics", "identifier": "statistics_popular_factions", "ru": "Популярные фракции", "en": "Popular Factions"},
            {"webpage": "statistics", "identifier": "statistics_daily_activity", "ru": "Активность по дням", "en": "Daily Activity"},
            {"webpage": "statistics", "identifier": "statistics_no_data", "ru": "Нет данных", "en": "No Data"},
            
            # Статистика кланов
            {"webpage": "clan-statistics", "identifier": "clan_statistics_title", "ru": "Статистика кланов", "en": "Clan Statistics"},
            {"webpage": "clan-statistics", "identifier": "clan_statistics_ranking", "ru": "Рейтинг кланов", "en": "Clan Ranking"},
            {"webpage": "clan-statistics", "identifier": "clan_statistics_members", "ru": "Участников", "en": "Members"},
            {"webpage": "clan-statistics", "identifier": "clan_statistics_wins", "ru": "Побед", "en": "Wins"},
            {"webpage": "clan-statistics", "identifier": "clan_statistics_losses", "ru": "Поражений", "en": "Losses"},
            {"webpage": "clan-statistics", "identifier": "clan_statistics_win_rate", "ru": "Винрейт", "en": "Win Rate"},
            {"webpage": "clan-statistics", "identifier": "clan_statistics_matches", "ru": "Матчей", "en": "Matches"},
            {"webpage": "clan-statistics", "identifier": "clan_statistics_top_wins", "ru": "Топ кланов по победам", "en": "Top Clans by Wins"},
            {"webpage": "clan-statistics", "identifier": "clan_statistics_top_winrate", "ru": "Топ кланов по винрейту", "en": "Top Clans by Win Rate"},
            {"webpage": "clan-statistics", "identifier": "clan_statistics_no_clans", "ru": "Нет данных о кланах", "en": "No Clan Data"},
            
            # Все матчи
            {"webpage": "all-matches", "identifier": "all_matches_title", "ru": "Все матчи", "en": "All Matches"},
            {"webpage": "all-matches", "identifier": "all_matches_filters", "ru": "Фильтры", "en": "Filters"},
            {"webpage": "all-matches", "identifier": "all_matches_faction", "ru": "Фракция", "en": "Faction"},
            {"webpage": "all-matches", "identifier": "all_matches_all_factions", "ru": "Все фракции", "en": "All Factions"},
            {"webpage": "all-matches", "identifier": "all_matches_player", "ru": "Игрок", "en": "Player"},
            {"webpage": "all-matches", "identifier": "all_matches_player_placeholder", "ru": "Введите имя игрока", "en": "Enter player name"},
            {"webpage": "all-matches", "identifier": "all_matches_date_from", "ru": "Дата с", "en": "Date From"},
            {"webpage": "all-matches", "identifier": "all_matches_date_to", "ru": "Дата по", "en": "Date To"},
            {"webpage": "all-matches", "identifier": "all_matches_list", "ru": "Матчи", "en": "Matches"},
            {"webpage": "all-matches", "identifier": "all_matches_date", "ru": "Дата", "en": "Date"},
            {"webpage": "all-matches", "identifier": "all_matches_winner", "ru": "Победитель", "en": "Winner"},
            {"webpage": "all-matches", "identifier": "all_matches_loser", "ru": "Проигравший", "en": "Loser"},
            {"webpage": "all-matches", "identifier": "all_matches_duration", "ru": "Длительность", "en": "Duration"},
            {"webpage": "all-matches", "identifier": "all_matches_map", "ru": "Карта", "en": "Map"},
            {"webpage": "all-matches", "identifier": "all_matches_not_found", "ru": "Матчи не найдены", "en": "Matches not found"},
            {"webpage": "all-matches", "identifier": "all_matches_previous", "ru": "Предыдущая", "en": "Previous"},
            {"webpage": "all-matches", "identifier": "all_matches_next", "ru": "Следующая", "en": "Next"},
            
            # Общие тексты
            {"webpage": "common", "identifier": "loading", "ru": "Загрузка...", "en": "Loading..."},
            {"webpage": "common", "identifier": "no_data", "ru": "Нет данных", "en": "No Data"},
        ]
        
        added_count = 0
        updated_count = 0
        
        for item in localization_data:
            # Проверяем, существует ли уже запись
            existing = db.query(Localization).filter(
                Localization.webpage == item["webpage"],
                Localization.identifier == item["identifier"]
            ).first()
            
            if existing:
                # Обновляем существующую запись
                existing.ru = item["ru"]
                existing.eng = item["en"]
                updated_count += 1
                print(f"  🔄 Обновлена: {item['webpage']}.{item['identifier']}")
            else:
                # Создаем новую запись
                new_localization = Localization(
                    webpage=item["webpage"],
                    identifier=item["identifier"],
                    ru=item["ru"],
                    eng=item["en"]
                )
                db.add(new_localization)
                added_count += 1
                print(f"  ➕ Добавлена: {item['webpage']}.{item['identifier']}")
        
        db.commit()
        print(f"\n✅ Локализация добавлена успешно!")
        print(f"  ➕ Добавлено записей: {added_count}")
        print(f"  🔄 Обновлено записей: {updated_count}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка при добавлении локализации: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    add_statistics_localization() 