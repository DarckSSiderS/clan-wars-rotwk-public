#!/usr/bin/env python3
"""
Скрипт для импорта матчей ROTWK Ennorath (1.9.7.6c) из API bfmeladder.com
Фильтрует только матчи с версией 1.9.7.6c и добавляет их в базу данных без дубликатов
"""

import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, engine
from app.models.match import Match
from sqlalchemy.orm import Session

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('import_rotwk_matches.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ROTWKMatchImporter:
    def __init__(self):
        self.proxy = os.getenv("PROXY_URL")
        self.api_url = "https://bfmeladder.com/api/replay"
        self.target_patch = "1.9.7.6c"
        self.target_game = "RotWK"
        
        # Маппинг фракций EN -> RU
        self.factions_en_to_ru = {
            "gondor": "Гондор",
            "rohan": "Рохан", 
            "isengard": "Изенгард",
            "mordor": "Мордор",
            "angmar": "Ангмар",
            "dwarves": "Гномы",
            "harad": "Харад",
            "arnor": "Арнор",
            "lothlorien": "Лотлориэн",
            "imladris": "Имладрис",
            "misty mountains": "Мглистые Горы",
        }
        
        # Уже русские названия
        self.factions_ru = {
            "Гондор", "Рохан", "Изенгард", "Мордор", "Ангмар", 
            "Гномы", "Харад", "Арнор", "Лотлориэн", "Имладрис", "Мглистые Горы"
        }
    
    def _normalize_faction(self, faction_name: str) -> str:
        """Нормализует название фракции к русскому варианту"""
        if not faction_name:
            return "Неизвестно"
        
        # Если уже русское название
        if faction_name in self.factions_ru:
            return faction_name
        
        # Конвертируем EN -> RU
        key = faction_name.strip().lower()
        return self.factions_en_to_ru.get(key, faction_name)
    
    def _parse_match_date(self, date_str: str) -> Optional[datetime]:
        """Парсит дату матча"""
        try:
            # Пробуем разные форматы даты
            formats = [
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ", 
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d"
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            
            logger.warning(f"Не удалось распарсить дату: {date_str}")
            return None
        except Exception as e:
            logger.error(f"Ошибка парсинга даты {date_str}: {e}")
            return None
    
    def _is_rotwk_ennorath_match(self, match_data: Dict) -> bool:
        """Проверяет, является ли матч ROTWK Ennorath (1.9.7.6c)"""
        try:
            # Проверяем версию патча
            patch = match_data.get('patch', '')
            if self.target_patch not in str(patch):
                return False
            
            # Проверяем игру
            game = match_data.get('game', '')
            if self.target_game not in str(game):
                return False
            
            return True
        except Exception as e:
            logger.error(f"Ошибка проверки матча: {e}")
            return False
    
    def _extract_match_data(self, match_data: Dict) -> Optional[Dict]:
        """Извлекает данные матча из JSON"""
        try:
            match_id = match_data.get('id', '')
            if not match_id:
                logger.warning("Матч без ID, пропускаем")
                return None
            
            # Получаем игроков
            players = match_data.get('players', [])
            if len(players) < 2:
                logger.warning(f"Матч {match_id} имеет менее 2 игроков, пропускаем")
                return None
            
            # Определяем победителя и проигравшего
            winner = None
            loser = None
            
            for player in players:
                if player.get('result') == 'victory':
                    winner = player
                elif player.get('result') == 'defeat':
                    loser = player
            
            if not winner or not loser:
                logger.warning(f"Матч {match_id} не имеет четкого победителя/проигравшего")
                return None
            
            # Извлекаем данные
            winner_name = winner.get('name', 'Неизвестно')
            winner_faction = self._normalize_faction(winner.get('faction', 'Неизвестно'))
            
            loser_name = loser.get('name', 'Неизвестно') 
            loser_faction = self._normalize_faction(loser.get('faction', 'Неизвестно'))
            
            # Дата матча
            match_date = match_data.get('date', '')
            parsed_date = self._parse_match_date(match_date)
            if not parsed_date:
                logger.warning(f"Матч {match_id} имеет неверную дату: {match_date}")
                return None
            
            # Дополнительные данные
            duration = match_data.get('duration', '')
            map_name = match_data.get('map', '')
            
            return {
                'match_id': str(match_id),
                'winner_player': winner_name,
                'winner_faction': winner_faction,
                'loser_player': loser_name,
                'loser_faction': loser_faction,
                'match_date': parsed_date,
                'duration': duration,
                'map_name': map_name,
                'game_mode': '1 vs 1',  # По умолчанию
                'patch_version': self.target_patch
            }
            
        except Exception as e:
            logger.error(f"Ошибка извлечения данных матча: {e}")
            return None
    
    async def _fetch_matches_from_api(self) -> List[Dict]:
        """Получает матчи из API через прокси"""
        connector = ProxyConnector.from_url(self.proxy) if self.proxy else aiohttp.TCPConnector()
        
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                logger.info("Подключение к API bfmeladder.com...")
                
                async with session.get(self.api_url) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка API: {response.status}")
                        return []
                    
                    # Получаем текст ответа
                    text_data = await response.text()
                    logger.info(f"Получен ответ длиной {len(text_data)} символов")
                    
                    # Пробуем распарсить как JSON
                    try:
                        data = json.loads(text_data)
                        logger.info(f"Получено {len(data)} матчей из API")
                        return data
                    except json.JSONDecodeError as json_error:
                        logger.error(f"Ошибка парсинга JSON: {json_error}")
                        logger.error(f"Первые 500 символов ответа: {text_data[:500]}")
                        return []
                    
        except Exception as e:
            logger.error(f"Ошибка получения данных из API: {e}")
            return []
    
    def _save_match_to_db(self, db: Session, match_data: Dict) -> bool:
        """Сохраняет матч в базу данных"""
        try:
            # Проверяем, не существует ли уже такой матч
            existing_match = db.query(Match).filter(Match.match_id == match_data['match_id']).first()
            if existing_match:
                logger.debug(f"Матч {match_data['match_id']} уже существует в базе")
                return False
            
            # Создаем новый матч
            new_match = Match(
                match_id=match_data['match_id'],
                winner_player=match_data['winner_player'],
                winner_faction=match_data['winner_faction'],
                loser_player=match_data['loser_player'],
                loser_faction=match_data['loser_faction'],
                match_date=match_data['match_date'],
                duration=match_data['duration'],
                game_mode=match_data['game_mode'],
                map_name=match_data['map_name'],
                patch_version=match_data['patch_version'],
                is_live=False
            )
            
            db.add(new_match)
            db.commit()
            logger.info(f"Сохранен матч {match_data['match_id']}: {match_data['winner_player']} vs {match_data['loser_player']}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения матча {match_data.get('match_id', 'unknown')}: {e}")
            db.rollback()
            return False
    
    async def import_matches(self):
        """Основная функция импорта"""
        logger.info("Начинаем импорт матчей ROTWK Ennorath (1.9.7.6c)...")
        
        # Получаем матчи из API
        all_matches = await self._fetch_matches_from_api()
        if not all_matches:
            logger.error("Не удалось получить матчи из API")
            return
        
        # Фильтруем только ROTWK Ennorath матчи
        rotwk_matches = []
        for match in all_matches:
            if self._is_rotwk_ennorath_match(match):
                rotwk_matches.append(match)
        
        logger.info(f"Найдено {len(rotwk_matches)} матчей ROTWK Ennorath из {len(all_matches)}")
        
        if not rotwk_matches:
            logger.info("Нет матчей ROTWK Ennorath для импорта")
            return
        
        # Подключаемся к базе данных
        db = SessionLocal()
        try:
            imported_count = 0
            skipped_count = 0
            
            for match in rotwk_matches:
                # Извлекаем данные матча
                match_data = self._extract_match_data(match)
                if not match_data:
                    skipped_count += 1
                    continue
                
                # Сохраняем в базу
                if self._save_match_to_db(db, match_data):
                    imported_count += 1
                else:
                    skipped_count += 1
            
            logger.info(f"Импорт завершен: {imported_count} импортировано, {skipped_count} пропущено")
            
        except Exception as e:
            logger.error(f"Ошибка импорта: {e}")
        finally:
            db.close()

async def main():
    """Главная функция"""
    importer = ROTWKMatchImporter()
    await importer.import_matches()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            # Игнорируем ошибку закрытого event loop в Windows
            pass
        else:
            raise
