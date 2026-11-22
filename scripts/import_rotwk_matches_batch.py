#!/usr/bin/env python3
"""
Скрипт для импорта матчей ROTWK Ennorath (1.9.7.6c) с пакетной обработкой
Оптимизирован для больших объемов данных
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
        logging.FileHandler('import_rotwk_matches_batch.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ROTWKMatchBatchImporter:
    def __init__(self, batch_size: int = 100):
        self.proxy = os.getenv("PROXY_URL")
        self.api_url = "https://bfmeladder.com/api/replay"
        self.target_patch = "1.9.7.6c"
        self.target_game = "RotWK"
        self.batch_size = batch_size
        
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
                return None
            
            # Получаем игроков
            players = match_data.get('players', [])
            if len(players) < 2:
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
                'game_mode': '1 vs 1',
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
    
    async def import_matches(self):
        """Основная функция импорта с пакетной обработкой"""
        logger.info("Начинаем импорт матчей ROTWK Ennorath (1.9.7.6c) с пакетной обработкой...")
        
        # Получаем матчи из API
        all_matches = await self._fetch_matches_from_api()
        if not all_matches:
            logger.error("Не удалось получить матчи из API")
            return
        
        # Фильтруем только ROTWK Ennorath матчи
        logger.info("Фильтрация матчей ROTWK Ennorath...")
        rotwk_matches = []
        for match in tqdm(all_matches, desc="Фильтрация"):
            if self._is_rotwk_ennorath_match(match):
                rotwk_matches.append(match)
        
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
            
            # Обрабатываем матчи пакетами
            total_imported = 0
            total_skipped = 0
            
            # Извлекаем данные матчей
            logger.info("Извлечение данных матчей...")
            matches_data = []
            for match in tqdm(rotwk_matches, desc="Извлечение данных"):
                match_data = self._extract_match_data(match)
                if match_data:
                    matches_data.append(match_data)
            
            logger.info(f"Извлечено {len(matches_data)} валидных матчей")
            
            # Сохраняем пакетами
            logger.info(f"Сохранение пакетами по {self.batch_size} матчей...")
            for i in range(0, len(matches_data), self.batch_size):
                batch = matches_data[i:i + self.batch_size]
                imported, skipped = self._save_matches_batch(db, batch, existing_ids)
                total_imported += imported
                total_skipped += skipped
                
                # Обновляем множество существующих ID
                for match_data in batch:
                    if match_data['match_id'] not in existing_ids:
                        existing_ids.add(match_data['match_id'])
                
                logger.info(f"Пакет {i//self.batch_size + 1}: {imported} импортировано, {skipped} пропущено")
            
            logger.info(f"Импорт завершен: {total_imported} импортировано, {total_skipped} пропущено")
            
        except Exception as e:
            logger.error(f"Ошибка импорта: {e}")
        finally:
            db.close()

async def main():
    """Главная функция"""
    # Можно настроить размер пакета
    batch_size = 100
    importer = ROTWKMatchBatchImporter(batch_size=batch_size)
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
