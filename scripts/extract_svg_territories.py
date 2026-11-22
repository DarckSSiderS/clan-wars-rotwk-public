#!/usr/bin/env python3
"""
Скрипт для автоматического извлечения всех территорий из SVG файла
"""

import re
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.repositories.territory_repository import TerritoryRepository
from app.schemas.territory import TerritoryCreate

def extract_territories_from_svg():
    """Извлекает все территории из SVG файла и создает их в базе данных"""
    
    # Читаем SVG файл
    svg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                           'frontend', 'public', 'map-interactive.svg')
    
    try:
        with open(svg_path, 'r', encoding='utf-8') as f:
            svg_content = f.read()
    except FileNotFoundError:
        print(f"❌ Файл {svg_path} не найден")
        return
    
    # Регулярное выражение для поиска path элементов с data-атрибутами
    pattern = r'<path[^>]*class="[^"]*interactive-region[^"]*"[^>]*d="([^"]*)"[^>]*data-name="([^"]*)"[^>]*data-region="([^"]*)"[^>]*data-description="([^"]*)"[^>]*/>'
    
    matches = re.findall(pattern, svg_content)
    
    if not matches:
        print("❌ Не найдено территорий в SVG файле")
        return
    
    print(f"🔍 Найдено {len(matches)} территорий в SVG файле")
    
    # Подключаемся к базе данных
    db = SessionLocal()
    repo = TerritoryRepository(db)
    
    created_count = 0
    skipped_count = 0
    
    try:
        for i, (svg_path_data, name, region, description) in enumerate(matches, 1):
            print(f"📝 Обрабатываем {i}/{len(matches)}: {name}")
            
            # Проверяем, существует ли уже территория с таким именем
            existing = repo.get_by_name(name)
            if existing:
                print(f"  ⚠️ Территория '{name}' уже существует, пропускаем")
                skipped_count += 1
                continue
            
            # Проверяем, существует ли уже территория с таким SVG path data
            existing_path = repo.get_by_svg_path_data(svg_path_data)
            if existing_path:
                print(f"  ⚠️ Территория с таким SVG path data уже существует, пропускаем")
                skipped_count += 1
                continue
            
            # Определяем базовые характеристики территории
            territory_data = {
                "name": name,
                "region": region,
                "description": description,
                "svg_path_data": svg_path_data,
                "resource_wealth": 100 + (i * 10),  # Базовое богатство
                "strategic_value": 1 + (i % 10),    # Стратегическая ценность 1-10
                "population": 100 + (i * 50),       # Население
                "fortifications": 1 + (i % 5),      # Укрепления 1-5
                "trade_routes": [region],           # Торговые пути
                "special_resources": ["basic"],     # Специальные ресурсы
                "climate": "temperate",             # Климат
                "terrain": "plains",                # Местность
                "status": "neutral"                 # Статус
            }
            
            # Создаем территорию
            territory_create = TerritoryCreate(**territory_data)
            territory = repo.create(territory_create)
            print(f"  ✅ Создана территория: {territory.name} (ID: {territory.id})")
            created_count += 1
        
        print("\n🎉 Извлечение территорий завершено!")
        print(f"📊 Статистика: создано {created_count}, пропущено {skipped_count}")
        
        # Показываем общую статистику
        stats = repo.get_territory_stats()
        print(f"📊 Общая статистика: всего территорий: {stats['total']}")
        
    except Exception as e:
        print(f"❌ Ошибка при обработке территорий: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    extract_territories_from_svg() 