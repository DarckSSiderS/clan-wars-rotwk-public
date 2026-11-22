#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для обновления имен игроков в базе данных
Использует данные с bfmeladder.com для сопоставления UUID с никнеймами
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector
from bs4 import BeautifulSoup
from urllib.parse import quote
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime
from app.database import SessionLocal
from app.models.match import Match
from app.models.user import User
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Legacy словарь для игроков, которые могли пропасть из текущего ладдера
LEGACY_PLAYERS = {
    # Добавьте сюда известные UUID -> никнейм соответствия
    # "uuid-here": "nickname-here",
}

class PlayerNameUpdater:
    def __init__(self):
        self.proxy = os.getenv("PROXY_URL")
        self.arena_id = "8a0e14c4-3204-4973-96e3-62ba9dc8526b"  # Ennorath arena
        self.gamemodes = ["1v1", "2v2", "3v3", "4v4", "FFA4", "FFA4Rings", "Randomizer"]
        self.users = {}  # UUID -> nickname mapping
        
    async def fetch_ladder_page(self, gamemode: str) -> str:
        """Получить HTML страницу ладдера"""
        url = f'https://bfmeladder.com/ladders?arena={quote(self.arena_id)}&gamemode={quote(gamemode)}'
        
        connector = ProxyConnector.from_url(self.proxy) if self.proxy else aiohttp.TCPConnector()
        timeout = aiohttp.ClientTimeout(total=30)
        
        try:
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                logger.info(f"Загружаем ладдер для режима: {gamemode}")
                async with session.get(url) as response:
                    if response.status == 200:
                        html = await response.text()
                        logger.info(f"✅ Успешно загружен ладдер для {gamemode}")
                        return html
                    else:
                        logger.error(f"❌ Ошибка загрузки ладдера {gamemode}: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"❌ Ошибка при загрузке ладдера {gamemode}: {e}")
            return None
    
    def parse_ladder_html(self, html: str, gamemode: str):
        """Парсить HTML ладдера и извлечь UUID -> nickname соответствия"""
        if not html:
            return
        
        try:
            bs = BeautifulSoup(html, 'html.parser')
            
            # Ищем таблицу с игроками
            table = bs.find('table')
            if not table:
                logger.warning(f"Не найдена таблица в ладдере {gamemode}")
                return
            
            rows = table.find_all('tr')[1:]  # Пропускаем заголовок
            count = 0
            
            for tr in rows:
                try:
                    # Ищем аватар для получения UUID
                    avatar_img = tr.find('img', class_='miniProfilePicture')
                    if not avatar_img or 'src' not in avatar_img.attrs:
                        continue
                    
                    # Извлекаем UUID из src аватара
                    src = avatar_img['src']
                    if 'id=' in src:
                        uid = src.split('id=')[-1].split('&')[0]
                    else:
                        continue
                    
                    # Ищем никнейм
                    username_span = tr.find('span', class_='ladderUsername')
                    if not username_span:
                        continue
                    
                    name = username_span.text.strip()
                    
                    if uid and name:
                        self.users[uid] = name
                        count += 1
                        logger.debug(f"Добавлен игрок: {uid} -> {name}")
                
                except Exception as e:
                    logger.warning(f"Ошибка при парсинге строки в {gamemode}: {e}")
                    continue
            
            logger.info(f"✅ Извлечено {count} игроков из ладдера {gamemode}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при парсинге HTML ладдера {gamemode}: {e}")
    
    async def load_all_ladders(self):
        """Загрузить все ладдеры и извлечь данные игроков"""
        logger.info("🔄 Загружаем данные со всех ладдеров...")
        
        for gamemode in self.gamemodes:
            html = await self.fetch_ladder_page(gamemode)
            if html:
                self.parse_ladder_html(html, gamemode)
            
            # Небольшая задержка между запросами
            await asyncio.sleep(1)
        
        # Добавляем legacy игроков
        self.users.update(LEGACY_PLAYERS)
        
        logger.info(f"📊 Всего собрано {len(self.users)} уникальных игроков")
    
    def get_player_name(self, uuid: str) -> str:
        """Получить никнейм игрока по UUID"""
        return self.users.get(uuid, uuid)  # Возвращаем UUID если никнейм не найден
    
    def update_matches_in_database(self):
        """Обновить имена игроков в базе данных"""
        db = SessionLocal()
        
        try:
            logger.info("🔄 Обновляем имена игроков в базе данных...")
            
            # Получаем все матчи
            matches = db.query(Match).all()
            logger.info(f"📊 Найдено {len(matches)} матчей для обработки")
            
            updated_count = 0
            
            for match in matches:
                updated = False
                
                # Проверяем winner_player
                if match.winner_player and match.winner_player in self.users:
                    new_winner_name = self.users[match.winner_player]
                    if new_winner_name != match.winner_player:
                        logger.info(f"Обновляем winner: {match.winner_player} -> {new_winner_name}")
                        match.winner_player = new_winner_name
                        updated = True
                
                # Проверяем loser_player
                if match.loser_player and match.loser_player in self.users:
                    new_loser_name = self.users[match.loser_player]
                    if new_loser_name != match.loser_player:
                        logger.info(f"Обновляем loser: {match.loser_player} -> {new_loser_name}")
                        match.loser_player = new_loser_name
                        updated = True
                
                if updated:
                    updated_count += 1
            
            if updated_count > 0:
                db.commit()
                logger.info(f"✅ Обновлено {updated_count} матчей")
            else:
                logger.info("ℹ️ Нет матчей для обновления")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении базы данных: {e}")
            db.rollback()
        finally:
            db.close()
    
    def show_statistics(self):
        """Показать статистику обновления"""
        db = SessionLocal()
        
        try:
            # Подсчитываем матчи с UUID
            uuid_matches = db.query(Match).filter(
                or_(
                    Match.winner_player.in_(list(self.users.keys())),
                    Match.loser_player.in_(list(self.users.keys()))
                )
            ).count()
            
            # Подсчитываем уникальных игроков в матчах
            all_players = set()
            matches = db.query(Match).all()
            for match in matches:
                if match.winner_player:
                    all_players.add(match.winner_player)
                if match.loser_player:
                    all_players.add(match.loser_player)
            
            uuid_players = [p for p in all_players if p in self.users]
            
            logger.info("📊 Статистика:")
            logger.info(f"   Всего игроков в ладдерах: {len(self.users)}")
            logger.info(f"   Уникальных игроков в матчах: {len(all_players)}")
            logger.info(f"   Игроков с UUID в матчах: {len(uuid_players)}")
            logger.info(f"   Матчей с UUID игроками: {uuid_matches}")
            
            if uuid_players:
                logger.info("   Примеры игроков с UUID:")
                for i, player in enumerate(uuid_players[:10]):
                    nickname = self.users.get(player, "Неизвестно")
                    logger.info(f"     {player} -> {nickname}")
                if len(uuid_players) > 10:
                    logger.info(f"     ... и еще {len(uuid_players) - 10} игроков")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении статистики: {e}")
        finally:
            db.close()

async def main():
    """Основная функция"""
    updater = PlayerNameUpdater()
    
    # Загружаем данные с ладдеров
    await updater.load_all_ladders()
    
    # Показываем статистику
    updater.show_statistics()
    
    # Обновляем базу данных
    updater.update_matches_in_database()
    
    logger.info("🎉 Обновление завершено!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            pass
        else:
            raise
