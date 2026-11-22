#!/usr/bin/env python3
"""
Скрипт для отладки получения LIVE матчей с сайта
"""

import asyncio
import sys
import os
import aiohttp
from aiohttp_socks import ProxyConnector
from bs4 import BeautifulSoup
import logging

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_live_matches():
    print("=== Отладка получения LIVE матчей ===\n")
    
    # Параметры API
    proxy = os.getenv("PROXY_URL")
    game = "RotWK"
    patch = "05a64473-c7f5-4fff-8e00-f30e06db9d96:1.9.7.6c"
    gamemode = "1 versus 1"
    
    try:
        connector = ProxyConnector.from_url(proxy) if proxy else aiohttp.TCPConnector()
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # Параметры запроса
            params = {
                'game': game,
                'patch': patch,
                'gamemode': gamemode,
                'page': 1,
                'limit': 100
            }
            
            url = f"https://bfmeladder.com/replays?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
            print(f"Запрашиваем URL: {url}")
            print(f"Параметры: {params}")
            
            async with session.get(url, params=params) as response:
                print(f"Статус ответа: {response.status}")
                
                if response.status == 200:
                    html_content = await response.text()
                    print(f"Размер HTML: {len(html_content)} символов")
                    
                    # Сохраняем HTML для анализа
                    with open("debug_live_matches.html", "w", encoding="utf-8") as f:
                        f.write(html_content)
                    print("HTML сохранен в debug_live_matches.html")
                    
                    # Парсим HTML
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Ищем все элементы с текстом "LIVE"
                    live_elements = soup.find_all(text=lambda text: text and 'LIVE' in text)
                    print(f"\nНайдено элементов с 'LIVE': {len(live_elements)}")
                    
                    for i, element in enumerate(live_elements[:10]):  # Показываем первые 10
                        print(f"{i+1}. '{element.strip()}' (родитель: {element.parent.name if element.parent else 'None'})")
                    
                    # Ищем ссылки с текстом "LIVE"
                    live_links = soup.find_all('a', string='LIVE')
                    print(f"\nНайдено ссылок с текстом 'LIVE': {len(live_links)}")
                    
                    # Ищем все карточки реплеев
                    replay_items = soup.find_all('div', class_='replay-item')
                    print(f"\nНайдено карточек реплеев: {len(replay_items)}")
                    
                    if replay_items:
                        print("\nАнализ первой карточки реплея:")
                        first_replay = replay_items[0]
                        print(f"HTML первой карточки: {first_replay.prettify()[:500]}...")
                        
                        # Ищем LIVE в первой карточке
                        live_in_first = first_replay.find_all(text=lambda text: text and 'LIVE' in text)
                        print(f"Элементов 'LIVE' в первой карточке: {len(live_in_first)}")
                        
                        for i, element in enumerate(live_in_first):
                            print(f"  {i+1}. '{element.strip()}'")
                    
                    # Ищем по другому паттерну
                    print("\nПоиск по другим паттернам:")
                    
                    # Ищем все элементы с классом, содержащим "live"
                    live_class_elements = soup.find_all(class_=lambda x: x and 'live' in x.lower())
                    print(f"Элементов с классом 'live': {len(live_class_elements)}")
                    
                    # Ищем все элементы с атрибутом, содержащим "live"
                    live_attr_elements = soup.find_all(attrs=lambda x: any('live' in str(v).lower() for v in x.values() if v))
                    print(f"Элементов с атрибутом 'live': {len(live_attr_elements)}")
                    
                else:
                    print(f"Ошибка HTTP: {response.status}")
                    
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_live_matches())
