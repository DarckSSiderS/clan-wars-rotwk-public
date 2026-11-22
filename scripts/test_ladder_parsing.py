#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестовый скрипт для проверки парсинга ладдера bfmeladder.com
"""

import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector
from bs4 import BeautifulSoup
from urllib.parse import quote
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_ladder_parsing():
    """Тестировать парсинг ладдера"""
    proxy = os.getenv("PROXY_URL")
    arena_id = "8a0e14c4-3204-4973-96e3-62ba9dc8526b"  # Ennorath arena
    gamemode = "1v1"  # Тестируем 1v1 режим
    
    url = f'https://bfmeladder.com/ladders?arena={quote(arena_id)}&gamemode={quote(gamemode)}'
    
    connector = ProxyConnector.from_url(proxy) if proxy else aiohttp.TCPConnector()
    timeout = aiohttp.ClientTimeout(total=30)
    
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            logger.info(f"Тестируем загрузку: {url}")
            
            async with session.get(url) as response:
                logger.info(f"Статус ответа: {response.status}")
                logger.info(f"Content-Type: {response.headers.get('content-type', 'unknown')}")
                
                if response.status == 200:
                    html = await response.text()
                    logger.info(f"Длина HTML: {len(html)} символов")
                    
                    # Парсим HTML
                    bs = BeautifulSoup(html, 'html.parser')
                    
                    # Ищем таблицу
                    table = bs.find('table')
                    if table:
                        logger.info("✅ Таблица найдена")
                        
                        # Ищем строки
                        rows = table.find_all('tr')
                        logger.info(f"Найдено строк: {len(rows)}")
                        
                        if len(rows) > 1:
                            # Парсим первую строку с данными (пропускаем заголовок)
                            first_row = rows[1]
                            logger.info("Парсим первую строку с данными:")
                            
                            # Ищем аватар
                            avatar_img = first_row.find('img', class_='miniProfilePicture')
                            if avatar_img:
                                src = avatar_img.get('src', '')
                                logger.info(f"Аватар src: {src}")
                                
                                if 'id=' in src:
                                    uid = src.split('id=')[-1].split('&')[0]
                                    logger.info(f"Извлеченный UUID: {uid}")
                                else:
                                    logger.warning("UUID не найден в src аватара")
                            else:
                                logger.warning("Аватар не найден")
                            
                            # Ищем никнейм
                            username_span = first_row.find('span', class_='ladderUsername')
                            if username_span:
                                name = username_span.text.strip()
                                logger.info(f"Никнейм: {name}")
                            else:
                                logger.warning("Никнейм не найден")
                            
                            # Показываем первые 5 игроков
                            logger.info("\nПервые 5 игроков:")
                            for i, row in enumerate(rows[1:6]):
                                try:
                                    avatar_img = row.find('img', class_='miniProfilePicture')
                                    username_span = row.find('span', class_='ladderUsername')
                                    
                                    if avatar_img and username_span:
                                        src = avatar_img.get('src', '')
                                        name = username_span.text.strip()
                                        
                                        if 'id=' in src:
                                            uid = src.split('id=')[-1].split('&')[0]
                                            logger.info(f"  {i+1}. {uid} -> {name}")
                                        else:
                                            logger.info(f"  {i+1}. UUID не найден -> {name}")
                                    else:
                                        logger.info(f"  {i+1}. Данные не найдены")
                                except Exception as e:
                                    logger.error(f"  {i+1}. Ошибка парсинга: {e}")
                        else:
                            logger.warning("Нет строк с данными в таблице")
                    else:
                        logger.error("❌ Таблица не найдена")
                        
                        # Показываем структуру HTML для отладки
                        logger.info("Структура HTML:")
                        for tag in bs.find_all()[:20]:  # Первые 20 тегов
                            logger.info(f"  {tag.name}: {tag.get('class', 'no-class')}")
                else:
                    logger.error(f"❌ Ошибка загрузки: {response.status}")
                    logger.error(f"Текст ответа: {await response.text()}")
    
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(test_ladder_parsing())
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            pass
        else:
            raise
