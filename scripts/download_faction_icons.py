#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Загрузка иконок фракций из BFME Ladder через прокси
"""

import aiohttp
import asyncio
import os
from aiohttp_socks import ProxyConnector
from pathlib import Path

# URL иконок фракций из BFME Ladder
FACTION_ICONS = {
    'gondor': 'https://bfmeladder.com/images/factions/gondor.png',
    'rohan': 'https://bfmeladder.com/images/factions/rohan.png',
    'isengard': 'https://bfmeladder.com/images/factions/isengard.png',
    'mordor': 'https://bfmeladder.com/images/factions/mordor.png',
    'angmar': 'https://bfmeladder.com/images/factions/angmar.png',
    'misty_mountains': 'https://bfmeladder.com/images/factions/misty_mountains.png',
    'lothlorien': 'https://bfmeladder.com/images/factions/lothlorien.png',
    'imladris': 'https://bfmeladder.com/images/factions/imladris.png',
    'arnor': 'https://bfmeladder.com/images/factions/arnor.png',
    'harad': 'https://bfmeladder.com/images/factions/harad.png'
}

async def download_faction_icon(session, faction, url):
    """Загружает одну иконку фракции"""
    try:
        print(f"Загружаю {faction}...")
        async with session.get(url) as response:
            if response.status == 200:
                content = await response.read()
                return faction, content
            else:
                print(f"❌ Ошибка HTTP {response.status} для {faction}")
                return faction, None
    except Exception as e:
        print(f"❌ Ошибка загрузки {faction}: {e}")
        return faction, None

async def download_faction_icons():
    """Загружает иконки фракций из BFME Ladder через прокси"""
    icons_dir = Path('frontend/public/icons/factions')
    icons_dir.mkdir(parents=True, exist_ok=True)
    
    print("Загрузка иконок фракций из BFME Ladder через прокси...")
    
    # Используем тот же прокси, что и в других частях проекта
    proxy = os.getenv("PROXY_URL")
    connector = ProxyConnector.from_url(proxy) if proxy else aiohttp.TCPConnector()
    
    async with aiohttp.ClientSession(connector=connector) as session:
        # Создаем задачи для всех иконок
        tasks = []
        for faction, url in FACTION_ICONS.items():
            task = download_faction_icon(session, faction, url)
            tasks.append(task)
        
        # Выполняем все задачи параллельно
        results = await asyncio.gather(*tasks)
        
        # Сохраняем загруженные иконки
        success_count = 0
        for faction, content in results:
            if content:
                icon_path = icons_dir / f"{faction}.png"
                with open(icon_path, 'wb') as f:
                    f.write(content)
                print(f"✅ {faction}.png сохранен ({len(content)} байт)")
                success_count += 1
            else:
                print(f"❌ Не удалось загрузить {faction}.png")
        
        print(f"Загрузка завершена! Успешно загружено: {success_count}/{len(FACTION_ICONS)}")

if __name__ == '__main__':
    asyncio.run(download_faction_icons())
