#!/usr/bin/env python3
"""
Скрипт для импорта матчей ROTWK Ennorath (1.9.7.6c) из API bfmeladder.com/api/replays
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
from tqdm import tqdm

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
        logging.FileHandler('import_rotwk_matches_api.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ROTWKMatchAPIImporter:
    def __init__(self):
        self.api_url = "https://bfmeladder.com/api/replays"
        self.proxy = os.getenv("PROXY_URL")
        
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
            if date_str.isdigit() and len(date_str) > 10:
                # Unix timestamp в миллисекундах
                timestamp_ms = int(date_str)
                timestamp_s = timestamp_ms / 1000
                return datetime.fromtimestamp(timestamp_s)
            elif '/' in date_str:
                # Формат YYYY/MM/DD HH:MM или YYYY/MM/DD
                if ' ' in date_str:
                    return datetime.strptime(date_str, "%Y/%m/%d %H:%M")
                else:
                    return datetime.strptime(date_str, "%Y/%m/%d")
            elif '.' in date_str:
                # Формат DD.MM.YYYY
                return datetime.strptime(date_str, "%d.%m.%Y")
        except Exception as e:
            logger.warning(f"Ошибка парсинга даты '{date_str}': {e}")
        return None
    
    def _is_rotwk_ennorath_match(self, match_data: Dict) -> bool:
        """Проверяет, является ли матч ROTWK Ennorath (1.9.7.6c)"""
        try:
            # Проверяем ID патча
            patch_id = match_data.get('PatchId', '')
            if "05a64473-c7f5-4fff-8e00-f30e06db9d96:1.9.7.6c" not in str(patch_id):
                return False
            
            # Проверяем название патча
            patch_name = match_data.get('PatchName', '')
            if "Ennorath (1.9.7.6c)" not in str(patch_name):
                return False
            
            # Проверяем игру
            game_name = match_data.get('GameName', '')
            if "RotWK" not in str(game_name):
                return False
            
            return True
        except Exception as e:
            logger.error(f"Ошибка проверки матча: {e}")
            return False
    
    def _extract_match_data(self, match_id: str, match_data: Dict) -> Optional[Dict]:
        """Извлекает данные матча из JSON"""
        try:
            # Получаем игроков
            players = match_data.get('Players', [])
            if len(players) < 2:
                logger.warning(f"Матч {match_id} имеет менее 2 игроков, пропускаем")
                return None
            
            # Определяем победителя и проигравшего
            winner = None
            loser = None
            
            for player in players:
                if player.get('IsWinner') == True:
                    winner = player
                elif player.get('IsWinner') == False:
                    loser = player
            
            if not winner or not loser:
                logger.warning(f"Матч {match_id} не имеет четкого победителя/проигравшего")
                return None
            
            # Извлекаем данные
            winner_name = winner.get('PlayerAccountUuid', 'Неизвестно')  # Используем UUID как имя
            winner_faction = self._normalize_faction(winner.get('FactionName', 'Неизвестно'))
            
            loser_name = loser.get('PlayerAccountUuid', 'Неизвестно')  # Используем UUID как имя
            loser_faction = self._normalize_faction(loser.get('FactionName', 'Неизвестно'))
            
            # Дата матча
            match_date = match_data.get('Date', '')
            parsed_date = self._parse_match_date(match_date)
            if not parsed_date:
                logger.warning(f"Матч {match_id} имеет неверную дату: {match_date}")
                return None
            
            # Дополнительные данные
            duration = match_data.get('Duration', '')
            map_name = match_data.get('MapName', '')
            gamemode = match_data.get('GamemodeName', '1 versus 1')
            patch_name = match_data.get('PatchName', '')
            
            return {
                'match_id': match_id,
                'winner_player': winner_name,
                'winner_faction': winner_faction,
                'loser_player': loser_name,
                'loser_faction': loser_faction,
                'match_date': parsed_date,
                'duration': duration,
                'map_name': map_name,
                'game_mode': gamemode,
                'patch_version': patch_name
            }
            
        except Exception as e:
            logger.error(f"Ошибка извлечения данных матча {match_id}: {e}")
            return None
    
    async def _fetch_matches_from_api(self) -> Dict:
        """Получает матчи из API через прокси"""
        connector = ProxyConnector.from_url(self.proxy) if self.proxy else aiohttp.TCPConnector()
        
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                logger.info("Подключение к API bfmeladder.com/api/replays...")
                
                async with session.get(self.api_url) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка API: {response.status}")
                        return {}
                    
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
                        return {}
                    
        except Exception as e:
            logger.error(f"Ошибка получения данных из API: {e}")
            return {}
    
    def _get_existing_match_ids(self, db: Session) -> set:
        """Получает список уже существующих ID матчей"""
        try:
            existing_matches = db.query(Match.match_id).all()
            return {match[0] for match in existing_matches}
        except Exception as e:
            logger.error(f"Ошибка получения существующих матчей: {e}")
            return set()
    
    def _save_matches_batch(self, db: Session, matches_data: List[Dict], existing_ids: set) -> tuple:
        """Сохраняет пакет матчей в базу данных"""
        imported_count = 0
        skipped_count = 0
        
        try:
            for match_data in matches_data:
                # Проверяем, не существует ли уже такой матч
                if match_data['match_id'] in existing_ids:
                    skipped_count += 1
                    continue
                
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
                imported_count += 1
            
            # Коммитим весь пакет
            db.commit()
            logger.info(f"Сохранен пакет: {imported_count} матчей")
            
        except Exception as e:
            logger.error(f"Ошибка сохранения пакета: {e}")
            db.rollback()
            return 0, len(matches_data)
        
        return imported_count, skipped_count
    
    async def import_matches(self, batch_size: int = 100):
        """Основная функция импорта"""
        logger.info("Начинаем импорт матчей ROTWK Ennorath (1.9.7.6c) из API...")
        
        # Получаем матчи из API
        all_matches = await self._fetch_matches_from_api()
        if not all_matches:
            logger.error("Не удалось получить матчи из API")
            return
        
        # Фильтруем только ROTWK Ennorath матчи
        logger.info("Фильтрация матчей ROTWK Ennorath...")
        rotwk_matches = {}
        for match_id, match_data in tqdm(all_matches.items(), desc="Фильтрация"):
            if self._is_rotwk_ennorath_match(match_data):
                rotwk_matches[match_id] = match_data
        
        logger.info(f"Найдено {len(rotwk_matches)} матчей ROTWK Ennorath из {len(all_matches)}")
        
        if not rotwk_matches:
            logger.info("Нет матчей ROTWK Ennorath для импорта")
            return
        
        # Подключаемся к базе данных
        db = SessionLocal()
        try:
            # Получаем существующие ID матчей
            logger.info("Получение существующих матчей из базы...")
            existing_ids = self._get_existing_match_ids(db)
            logger.info(f"Найдено {len(existing_ids)} существующих матчей")
            
            # Извлекаем данные матчей
            logger.info("Извлечение данных матчей...")
            matches_data = []
            for match_id, match_data in tqdm(rotwk_matches.items(), desc="Извлечение данных"):
                match_data_extracted = self._extract_match_data(match_id, match_data)
                if match_data_extracted:
                    matches_data.append(match_data_extracted)
            
            logger.info(f"Извлечено {len(matches_data)} валидных матчей")
            
            # Сохраняем пакетами
            logger.info(f"Сохранение пакетами по {batch_size} матчей...")
            total_imported = 0
            total_skipped = 0
            
            for i in range(0, len(matches_data), batch_size):
                batch = matches_data[i:i + batch_size]
                imported, skipped = self._save_matches_batch(db, batch, existing_ids)
                total_imported += imported
                total_skipped += skipped
                
                # Обновляем множество существующих ID
                for match_data in batch:
                    if match_data['match_id'] not in existing_ids:
                        existing_ids.add(match_data['match_id'])
                
                logger.info(f"Пакет {i//batch_size + 1}: {imported} импортировано, {skipped} пропущено")
            
            logger.info(f"Импорт завершен: {total_imported} импортировано, {total_skipped} пропущено")
            
        except Exception as e:
            logger.error(f"Ошибка импорта: {e}")
        finally:
            db.close()

async def main():
    """Главная функция"""
    importer = ROTWKMatchAPIImporter()
    await importer.import_matches(batch_size=100)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            # Игнорируем ошибку закрытого event loop в Windows
            pass
        else:
            raise
