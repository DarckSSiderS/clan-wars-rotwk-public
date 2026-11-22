#!/usr/bin/env python3
"""
Скрипт для импорта матчей ROTWK Ennorath (1.9.7.6c) из bfmeladder.com
Использует HTML парсинг для получения данных о матчах
"""

import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector
from bs4 import BeautifulSoup
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
        logging.FileHandler('import_rotwk_matches_correct.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ROTWKMatchImporter:
    def __init__(self):
        self.ladder_base = "https://bfmeladder.com/replays"
        self.game = "RotWK"
        self.patch = "05a64473-c7f5-4fff-8e00-f30e06db9d96:1.9.7.6c"
        self.gamemode = "1 versus 1"
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
        
        # Маппинг URL иконок на фракции
        self.icon_mappings = {
            '014c1ebf-1d53-4b29-9914-1fa3e44dae0c.png': 'Харад',
            '806c09f6-3abf-479b-b97a-b856d80b0e02.png': 'Изенгард',
            '73a97e8e-bd4c-450c-87d9-4596e7b68e59.png': 'Мглистые Горы',
            'e464285a-5cc1-457a-b1f6-012c5b10aa25.png': 'Гондор',
            '0afa17d0-7d6f-4b42-a9f0-ad7dd2ac44bf.png': 'Мордор',
            'fe8eff0d-d1d6-459c-8c0f-2ca1a38ee35f.png': 'Лотлориэн',
            'a983b2bd-64eb-412d-9872-5e35279b3ab0.png': 'Имладрис',
            '08217ec7-0c2d-4c68-9afa-e0c98f2d9c8d.png': 'Арнор',
            'efcd9306-00a2-4dfd-8773-7ed8bce73e1b.png': 'Рохан',
            '69eedfea-67c6-4ada-981b-8764a1045d44.png': 'Ангмар',
            '55329afc-4393-475d-96ba-d3b8f3f7703c.png': 'Гномы',
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
    
    def _get_faction_from_icon_url(self, icon_url: str) -> Optional[str]:
        """Определяет фракцию по URL иконки армии"""
        # Извлекаем имя файла из URL
        if '/' in icon_url:
            filename = icon_url.split('/')[-1]
        else:
            filename = icon_url
        
        faction = self.icon_mappings.get(filename)
        if not faction:
            logger.info(f"Неизвестная иконка фракции: {filename}")
            
        return faction
    
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
    
    def _extract_duration(self, replay_item) -> Optional[str]:
        """Извлекает длительность матча"""
        try:
            # Ищем элемент с текстом "Duration"
            duration_elements = replay_item.find_all('div', string=lambda text: text and 'Duration' in text)
            for duration_element in duration_elements:
                parent = duration_element.find_parent()
                if parent:
                    # Ищем соседний элемент с длительностью
                    duration_value = parent.find_next_sibling()
                    if duration_value:
                        return duration_value.get_text(strip=True)
        except Exception as e:
            logger.warning(f"Ошибка извлечения длительности: {e}")
        return None
    
    def _extract_map_name(self, replay_item) -> Optional[str]:
        """Извлекает название карты"""
        try:
            # Ищем блок с картой
            map_block = replay_item.find('div', {'class': 'mapImageBlock'})
            if map_block:
                # Название карты обычно находится в div под изображением
                map_name_div = map_block.find('div', style=lambda value: value and 'font-weight: 800' in value and 'text-align: center' in value)
                if map_name_div:
                    return map_name_div.get_text(strip=True)
        except Exception as e:
            logger.warning(f"Ошибка извлечения названия карты: {e}")
        return None
    
    def _extract_players_from_section(self, section) -> List[tuple]:
        """Извлекает игроков и их фракции из секции Winners или Losers"""
        players = []
        
        # Ищем контейнеры с игроками (обычно div с flex align-items: center)
        player_containers = section.find_all('div', style=lambda x: x and 'align-items: center' in x)
        
        for container in player_containers:
            try:
                # Ищем имя игрока (обычно в div с font-weight: 800)
                player_name_div = container.find('div', style=lambda x: x and 'font-weight: 800' in x)
                if not player_name_div:
                    continue
                
                # Ищем иконку армии рядом с именем игрока
                army_icon = player_name_div.find('img', {'class': 'armyIcon'})
                if not army_icon:
                    continue
                
                # Извлекаем имя игрока (убираем иконку из текста)
                player_name = player_name_div.get_text(strip=True)
                
                # Определяем фракцию по иконке
                faction = self._get_faction_from_icon_url(army_icon.get('src', ''))
                if faction:
                    players.append((player_name, faction))
                    
            except Exception as e:
                logger.warning(f"Ошибка извлечения игрока: {e}")
                continue
        
        return players
    
    def _extract_match_data_from_replay_item(self, replay_item) -> Optional[Dict]:
        """Извлекает данные матча из HTML элемента реплея"""
        try:
            # Получаем ID матча из атрибута id элемента
            match_id = replay_item.get('id', '')
            if not match_id:
                return None
            
            # Проверяем, не является ли матч LIVE
            live_link = replay_item.find('a', string='LIVE')
            is_live = live_link is not None
            if is_live:
                return None  # Пропускаем LIVE матчи
            
            # Извлекаем дату матча
            date_element = replay_item.find('div', {'class': 'unixDate'})
            if date_element:
                match_date = date_element.get_text(strip=True)
            else:
                return None
            
            # Парсим дату
            parsed_date = self._parse_match_date(match_date)
            if not parsed_date:
                return None
            
            # Ищем секции Winners и Losers
            winners_section = None
            losers_section = None
            
            # Находим текст "Winners" и "Losers"
            big_texts = replay_item.find_all('div', {'class': 'bigText'})
            for big_text in big_texts:
                if 'Winners' in big_text.get_text():
                    winners_section = big_text.find_parent()
                elif 'Losers' in big_text.get_text():
                    losers_section = big_text.find_parent()
            
            if not winners_section or not losers_section:
                return None
            
            # Извлекаем игроков и их фракции
            winner_players = self._extract_players_from_section(winners_section)
            loser_players = self._extract_players_from_section(losers_section)
            
            if not winner_players or not loser_players:
                return None
            
            # Берем первого победителя и первого проигравшего
            winner_name, winner_faction = winner_players[0]
            loser_name, loser_faction = loser_players[0]
            
            # Нормализуем фракции
            winner_faction = self._normalize_faction(winner_faction)
            loser_faction = self._normalize_faction(loser_faction)
            
            # Извлекаем дополнительную информацию о матче
            duration = self._extract_duration(replay_item)
            map_name = self._extract_map_name(replay_item)
            
            return {
                'match_id': match_id,
                'winner_player': winner_name,
                'winner_faction': winner_faction,
                'loser_player': loser_name,
                'loser_faction': loser_faction,
                'match_date': parsed_date,
                'duration': duration,
                'map_name': map_name,
                'game_mode': self.gamemode,
                'patch_version': self.patch
            }
            
        except Exception as e:
            logger.error(f"Ошибка извлечения данных матча: {e}")
            return None
    
    async def _fetch_matches_from_page(self, page: int = 1, limit: int = 100) -> List[Dict]:
        """Получает матчи с определенной страницы"""
        connector = ProxyConnector.from_url(self.proxy) if self.proxy else aiohttp.TCPConnector()
        timeout = aiohttp.ClientTimeout(total=30)
        
        try:
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                # Параметры запроса
                params = {
                    'game': self.game,
                    'patch': self.patch,
                    'gamemode': self.gamemode,
                    'page': page,
                    'limit': limit
                }
                
                url = f"{self.ladder_base}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
                logger.info(f"Запрос страницы {page}: {url}")
                
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка HTTP {response.status}: {response.reason}")
                        return []
                    
                    html_content = await response.text()
                    
                    # Парсим HTML для извлечения данных о реплеях
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Ищем карточки реплеев
                    replay_items = soup.find_all('div', {'class': 'replayItem'})
                    if not replay_items:
                        logger.warning(f"Карточки реплеев не найдены на странице {page}")
                        return []
                    
                    logger.info(f"Найдено {len(replay_items)} реплеев на странице {page}")
                    
                    # Извлекаем данные из каждого реплея
                    matches_data = []
                    for replay_item in replay_items:
                        match_data = self._extract_match_data_from_replay_item(replay_item)
                        if match_data:
                            matches_data.append(match_data)
                    
                    logger.info(f"Извлечено {len(matches_data)} валидных матчей с страницы {page}")
                    return matches_data
                    
        except Exception as e:
            logger.error(f"Ошибка получения матчей со страницы {page}: {e}")
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
    
    async def import_matches(self, max_pages: int = 10, batch_size: int = 100):
        """Основная функция импорта"""
        logger.info("Начинаем импорт матчей ROTWK Ennorath (1.9.7.6c)...")
        
        # Подключаемся к базе данных
        db = SessionLocal()
        try:
            # Получаем существующие ID матчей
            logger.info("Получение существующих матчей из базы...")
            existing_ids = self._get_existing_match_ids(db)
            logger.info(f"Найдено {len(existing_ids)} существующих матчей")
            
            total_imported = 0
            total_skipped = 0
            
            # Обрабатываем страницы
            for page in range(1, max_pages + 1):
                logger.info(f"Обработка страницы {page}/{max_pages}...")
                
                # Получаем матчи с текущей страницы
                matches_data = await self._fetch_matches_from_page(page=page, limit=100)
                if not matches_data:
                    logger.info(f"На странице {page} нет матчей, останавливаемся")
                    break
                
                # Сохраняем пакетами
                for i in range(0, len(matches_data), batch_size):
                    batch = matches_data[i:i + batch_size]
                    imported, skipped = self._save_matches_batch(db, batch, existing_ids)
                    total_imported += imported
                    total_skipped += skipped
                    
                    # Обновляем множество существующих ID
                    for match_data in batch:
                        if match_data['match_id'] not in existing_ids:
                            existing_ids.add(match_data['match_id'])
                    
                    logger.info(f"Страница {page}, пакет {i//batch_size + 1}: {imported} импортировано, {skipped} пропущено")
                
                # Небольшая пауза между страницами
                await asyncio.sleep(1)
            
            logger.info(f"Импорт завершен: {total_imported} импортировано, {total_skipped} пропущено")
            
        except Exception as e:
            logger.error(f"Ошибка импорта: {e}")
        finally:
            db.close()

async def main():
    """Главная функция"""
    importer = ROTWKMatchImporter()
    await importer.import_matches(max_pages=5, batch_size=50)  # Начинаем с небольшого количества

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            # Игнорируем ошибку закрытого event loop в Windows
            pass
        else:
            raise
