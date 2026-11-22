#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Загрузка иконок фракций из BFME Ladder через прокси (версия 2)
"""

import aiohttp
import asyncio
import os
from aiohttp_socks import ProxyConnector
from pathlib import Path

# Альтернативные URL иконок фракций (размер 25x25)
FACTION_ICONS = {
    'gondor': [
        'https://bfmeladder.com/images/factions/gondor.png',
        'https://bfmeladder.com/static/images/factions/gondor.png',
        'https://bfmeladder.com/assets/images/factions/gondor.png',
        'https://bfmeladder.com/img/factions/gondor.png'
    ],
    'rohan': [
        'https://bfmeladder.com/images/factions/rohan.png',
        'https://bfmeladder.com/static/images/factions/rohan.png',
        'https://bfmeladder.com/assets/images/factions/rohan.png',
        'https://bfmeladder.com/img/factions/rohan.png'
    ],
    'isengard': [
        'https://bfmeladder.com/images/factions/isengard.png',
        'https://bfmeladder.com/static/images/factions/isengard.png',
        'https://bfmeladder.com/assets/images/factions/isengard.png',
        'https://bfmeladder.com/img/factions/isengard.png'
    ],
    'mordor': [
        'https://bfmeladder.com/images/factions/mordor.png',
        'https://bfmeladder.com/static/images/factions/mordor.png',
        'https://bfmeladder.com/assets/images/factions/mordor.png',
        'https://bfmeladder.com/img/factions/mordor.png'
    ],
    'angmar': [
        'https://bfmeladder.com/images/factions/angmar.png',
        'https://bfmeladder.com/static/images/factions/angmar.png',
        'https://bfmeladder.com/assets/images/factions/angmar.png',
        'https://bfmeladder.com/img/factions/angmar.png'
    ],
    'misty_mountains': [
        'https://bfmeladder.com/images/factions/misty_mountains.png',
        'https://bfmeladder.com/static/images/factions/misty_mountains.png',
        'https://bfmeladder.com/assets/images/factions/misty_mountains.png',
        'https://bfmeladder.com/img/factions/misty_mountains.png'
    ],
    'lothlorien': [
        'https://bfmeladder.com/images/factions/lothlorien.png',
        'https://bfmeladder.com/static/images/factions/lothlorien.png',
        'https://bfmeladder.com/assets/images/factions/lothlorien.png',
        'https://bfmeladder.com/img/factions/lothlorien.png'
    ],
    'imladris': [
        'https://bfmeladder.com/images/factions/imladris.png',
        'https://bfmeladder.com/static/images/factions/imladris.png',
        'https://bfmeladder.com/assets/images/factions/imladris.png',
        'https://bfmeladder.com/img/factions/imladris.png'
    ],
    'arnor': [
        'https://bfmeladder.com/images/factions/arnor.png',
        'https://bfmeladder.com/static/images/factions/arnor.png',
        'https://bfmeladder.com/assets/images/factions/arnor.png',
        'https://bfmeladder.com/img/factions/arnor.png'
    ],
    'harad': [
        'https://bfmeladder.com/images/factions/harad.png',
        'https://bfmeladder.com/static/images/factions/harad.png',
        'https://bfmeladder.com/assets/images/factions/harad.png',
        'https://bfmeladder.com/img/factions/harad.png'
    ]
}

async def download_faction_icon(session, faction, urls):
    """Загружает одну иконку фракции, пробуя разные URL"""
    print(f"\n🎯 Попытка загрузки {faction}:")
    
    for i, url in enumerate(urls, 1):
        try:
            print(f"  {i}. Пробуем: {url}")
            async with session.get(url, timeout=10) as response:
                print(f"     Статус: {response.status}")
                if response.status == 200:
                    content = await response.read()
                    print(f"     Размер: {len(content)} байт")
                    
                    # Проверяем, что это действительно изображение
                    if len(content) > 100 and content.startswith(b'\x89PNG'):
                        print(f"     ✅ Успешно загружено с {url}")
                        return faction, content
                    else:
                        print(f"     ❌ Неверный формат или слишком маленький файл")
                else:
                    print(f"     ❌ HTTP ошибка: {response.status}")
                    
        except asyncio.TimeoutError:
            print(f"     ❌ Таймаут для {url}")
        except Exception as e:
            print(f"     ❌ Ошибка: {e}")
    
    print(f"  ❌ Не удалось загрузить {faction} ни с одного URL")
    return faction, None

async def download_faction_icons():
    """Загружает иконки фракций из BFME Ladder через прокси"""
    icons_dir = Path('frontend/public/icons/factions')
    icons_dir.mkdir(parents=True, exist_ok=True)
    
    print("🚀 Загрузка иконок фракций из BFME Ladder через прокси...")
    print("📋 Список всех URL для проверки:")
    
    for faction, urls in FACTION_ICONS.items():
        print(f"\n{faction.upper()}:")
        for i, url in enumerate(urls, 1):
            print(f"  {i}. {url}")
    
    # Используем тот же прокси, что и в других частях проекта
    proxy = os.getenv("PROXY_URL")
    connector = ProxyConnector.from_url(proxy) if proxy else aiohttp.TCPConnector()
    
    async with aiohttp.ClientSession(connector=connector) as session:
        # Создаем задачи для всех иконок
        tasks = []
        for faction, urls in FACTION_ICONS.items():
            task = download_faction_icon(session, faction, urls)
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
                print(f"\n✅ {faction}.png сохранен ({len(content)} байт)")
                success_count += 1
            else:
                print(f"\n❌ Не удалось загрузить {faction}.png")
        
        print(f"\n📊 Загрузка завершена! Успешно загружено: {success_count}/{len(FACTION_ICONS)}")

if __name__ == '__main__':
    asyncio.run(download_faction_icons())
