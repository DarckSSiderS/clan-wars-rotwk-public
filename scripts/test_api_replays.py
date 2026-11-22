#!/usr/bin/env python3
"""
Тестовый скрипт для проверки API bfmeladder.com/api/replays
"""

import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector
import json
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_api():
    proxy = os.getenv("PROXY_URL")
    api_url = "https://bfmeladder.com/api/replays"
    
    connector = ProxyConnector.from_url(proxy) if proxy else aiohttp.TCPConnector()
    timeout = aiohttp.ClientTimeout(total=60)  # Увеличиваем таймаут
    
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            logger.info("Подключение к API bfmeladder.com/api/replays...")
            
            async with session.get(api_url) as response:
                logger.info(f"Статус ответа: {response.status}")
                logger.info(f"Content-Type: {response.headers.get('content-type', 'unknown')}")
                
                # Получаем первые 1000 символов для анализа
                text_data = await response.text()
                logger.info(f"Длина ответа: {len(text_data)} символов")
                logger.info(f"Первые 1000 символов ответа:")
                logger.info(text_data[:1000])
                
                # Пробуем распарсить как JSON
                try:
                    data = json.loads(text_data)
                    logger.info(f"✅ JSON успешно распарсен")
                    logger.info(f"Количество записей: {len(data)}")
                    
                    # Проверяем первые несколько записей
                    count = 0
                    for match_id, match_data in data.items():
                        if count >= 3:  # Показываем только первые 3 записи
                            break
                        logger.info(f"Матч {match_id}:")
                        logger.info(f"  PatchId: {match_data.get('PatchId', 'N/A')}")
                        logger.info(f"  PatchName: {match_data.get('PatchName', 'N/A')}")
                        logger.info(f"  GameName: {match_data.get('GameName', 'N/A')}")
                        logger.info(f"  Players: {len(match_data.get('Players', []))}")
                        count += 1
                    
                except json.JSONDecodeError as json_error:
                    logger.error(f"❌ Ошибка парсинга JSON: {json_error}")
                    logger.error(f"Позиция ошибки: {json_error.pos}")
                    logger.error(f"Строка с ошибкой: {json_error.lineno}")
                    logger.error(f"Колонка с ошибкой: {json_error.colno}")
                    logger.error(f"Контекст вокруг ошибки:")
                    start = max(0, json_error.pos - 50)
                    end = min(len(text_data), json_error.pos + 50)
                    logger.error(text_data[start:end])
                    
    except Exception as e:
        logger.error(f"Ошибка подключения: {e}")

async def main():
    await test_api()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            pass
        else:
            raise
