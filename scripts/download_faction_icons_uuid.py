#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Загрузка иконок фракций из BFME Ladder через прокси (используя UUID)
"""

import aiohttp
import asyncio
import os
from aiohttp_socks import ProxyConnector
from pathlib import Path

# UUID иконок фракций из ladder_service.py
FACTION_ICONS = {
    'gondor': 'e464285a-5cc1-457a-b1f6-012c5b10aa25.png',
    'rohan': 'efcd9306-00a2-4dfd-8773-7ed8bce73e1b.png',
    'isengard': '806c09f6-3abf-479b-b97a-b856d80b0e02.png',
    'mordor': '0afa17d0-7d6f-4b42-a9f0-ad7dd2ac44bf.png',
    'angmar': '69eedfea-67c6-4ada-981b-8764a1045d44.png',
    'misty_mountains': '73a97e8e-bd4c-450c-87d9-4596e7b68e59.png',
    'lothlorien': 'fe8eff0d-d1d6-459c-8c0f-2ca1a38ee35f.png',
    'imladris': 'a983b2bd-64eb-412d-9872-5e35279b3ab0.png',
    'arnor': '08217ec7-0c2d-4c68-9afa-e0c98f2d9c8d.png',
    'harad': '014c1ebf-1d53-4b29-9914-1fa3e44dae0c.png'
}

async def download_faction_icon(session, faction, uuid_filename):
    """Загружает одну иконку фракции по UUID"""
    try:
        # Пробуем разные базовые URL для иконок
        base_urls = [
            'https://bfmeladder.com/images/',
            'https://bfmeladder.com/static/images/',
            'https://bfmeladder.com/assets/images/',
            'https://bfmeladder.com/img/',
            'https://bfmeladder.com/uploads/',
            'https://bfmeladder.com/media/'
        ]
        
        print(f"\n🎯 Попытка загрузки {faction} ({uuid_filename}):")
        
        for i, base_url in enumerate(base_urls, 1):
            url = base_url + uuid_filename
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
        
    except Exception as e:
        print(f"❌ Ошибка загрузки {faction}: {e}")
        return faction, None

async def download_faction_icons():
    """Загружает иконки фракций из BFME Ladder через прокси"""
    icons_dir = Path('frontend/public/icons/factions')
    icons_dir.mkdir(parents=True, exist_ok=True)
    
    print("🚀 Загрузка иконок фракций из BFME Ladder через прокси (UUID)...")
    print("📋 Список всех UUID для проверки:")
    
    for faction, uuid_filename in FACTION_ICONS.items():
        print(f"\n{faction.upper()}: {uuid_filename}")
        for i, base_url in enumerate([
            'https://bfmeladder.com/images/',
            'https://bfmeladder.com/static/images/',
            'https://bfmeladder.com/assets/images/',
            'https://bfmeladder.com/img/',
            'https://bfmeladder.com/uploads/',
            'https://bfmeladder.com/media/'
        ], 1):
            print(f"  {i}. {base_url}{uuid_filename}")
    
    # Используем тот же прокси, что и в других частях проекта
    proxy = os.getenv("PROXY_URL")
    connector = ProxyConnector.from_url(proxy) if proxy else aiohttp.TCPConnector()
    
    async with aiohttp.ClientSession(connector=connector) as session:
        # Создаем задачи для всех иконок
        tasks = []
        for faction, uuid_filename in FACTION_ICONS.items():
            task = download_faction_icon(session, faction, uuid_filename)
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
