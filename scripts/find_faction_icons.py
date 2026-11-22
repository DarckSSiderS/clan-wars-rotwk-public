#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Поиск иконок фракций на сайте BFME Ladder
"""

import aiohttp
import asyncio
import os
from aiohttp_socks import ProxyConnector
from bs4 import BeautifulSoup
import re

async def find_faction_icons():
    """Ищет иконки фракций на сайте BFME Ladder"""
    print("🔍 Поиск иконок фракций на сайте BFME Ladder...")
    
    # Используем тот же прокси, что и в других частях проекта
    proxy = os.getenv("PROXY_URL")
    connector = ProxyConnector.from_url(proxy) if proxy else aiohttp.TCPConnector()
    
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            # Загружаем главную страницу
            print("📄 Загружаем главную страницу...")
            async with session.get("https://bfmeladder.com/") as response:
                if response.status == 200:
                    content = await response.text()
                    print(f"✅ Главная страница загружена ({len(content)} символов)")
                    
                    # Ищем все изображения
                    soup = BeautifulSoup(content, 'html.parser')
                    images = soup.find_all('img')
                    
                    print(f"🔍 Найдено {len(images)} изображений на странице")
                    
                    # Ищем изображения, связанные с фракциями
                    faction_images = []
                    for img in images:
                        src = img.get('src', '')
                        alt = img.get('alt', '')
                        title = img.get('title', '')
                        
                        # Проверяем, содержит ли изображение упоминание фракций
                        faction_keywords = ['gondor', 'rohan', 'isengard', 'mordor', 'angmar', 
                                          'misty', 'lothlorien', 'imladris', 'arnor', 'harad',
                                          'faction', 'фракция']
                        
                        if any(keyword in src.lower() or keyword in alt.lower() or keyword in title.lower() 
                               for keyword in faction_keywords):
                            faction_images.append({
                                'src': src,
                                'alt': alt,
                                'title': title
                            })
                            print(f"🎯 Найдено изображение фракции: {src} (alt: {alt}, title: {title})")
                    
                    print(f"\n📊 Найдено {len(faction_images)} изображений фракций")
                    
                    # Также ищем в CSS и JavaScript файлах
                    print("\n🔍 Поиск в CSS и JS файлах...")
                    
                    # Ищем CSS файлы
                    css_links = soup.find_all('link', rel='stylesheet')
                    for css_link in css_links[:3]:  # Проверяем первые 3 CSS файла
                        css_href = css_link.get('href')
                        if css_href:
                            try:
                                print(f"📄 Проверяем CSS: {css_href}")
                                async with session.get(css_href) as css_response:
                                    if css_response.status == 200:
                                        css_content = await css_response.text()
                                        # Ищем упоминания фракций в CSS
                                        faction_matches = re.findall(r'faction[^}]*', css_content, re.IGNORECASE)
                                        if faction_matches:
                                            print(f"🎯 Найдены упоминания фракций в CSS: {faction_matches[:5]}")
                            except Exception as e:
                                print(f"❌ Ошибка при загрузке CSS {css_href}: {e}")
                    
                    # Ищем JavaScript файлы
                    js_scripts = soup.find_all('script', src=True)
                    for js_script in js_scripts[:3]:  # Проверяем первые 3 JS файла
                        js_src = js_script.get('src')
                        if js_src:
                            try:
                                print(f"📄 Проверяем JS: {js_src}")
                                async with session.get(js_src) as js_response:
                                    if js_response.status == 200:
                                        js_content = await js_response.text()
                                        # Ищем упоминания фракций в JS
                                        faction_matches = re.findall(r'faction[^;]*', js_content, re.IGNORECASE)
                                        if faction_matches:
                                            print(f"🎯 Найдены упоминания фракций в JS: {faction_matches[:5]}")
                            except Exception as e:
                                print(f"❌ Ошибка при загрузке JS {js_src}: {e}")
                    
                else:
                    print(f"❌ Ошибка загрузки главной страницы: {response.status}")
                    
        except Exception as e:
            print(f"❌ Ошибка: {e}")

if __name__ == '__main__':
    asyncio.run(find_faction_icons())
