#!/usr/bin/env python3
"""
Скрипт для заполнения базы данных всеми территориями из SVG
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.repositories.territory_repository import TerritoryRepository
from app.schemas.territory import TerritoryCreate

def seed_all_territories():
    """Заполняет базу данных всеми территориями из SVG"""
    db = SessionLocal()
    repo = TerritoryRepository(db)
    
    # Все территории из SVG файла
    territories_data = [
        # Первые 5 территорий (уже есть в базе)
        {
            "name": "Рун",
            "region": "rhun",
            "description": "Рун — восточные земли и побережья Моря Рун.",
            "svg_path_data": "M3362.1,599.9c0,0-41-7-70-3s-92,14-108,9s-36-16-60-10s-32,17-53,17s-53-8-73-3s-48.6,21.6-48.6,21.6 s-22.4,19.4-20.4,47.4s-4,40-9,48s-6,41-6,41s3.4,39.7,37.4,56.7s42,13,47,51s13,64,37,74c0,0,37-6,66-53s31-56,59-63s34-22,72-10 s80,18,107,18s35-7,68,24s33,33,47,32s37-6,3-52s-34-61-24-83s-6-29-8-52s10-29-3-42S3390.7,644.2,3362.1,599.9z",
            "resource_wealth": 150,
            "strategic_value": 8,
            "population": 500,
            "fortifications": 3,
            "trade_routes": ["rivendell", "misty_mountains"],
            "special_resources": ["fresh_water", "defensive_position"],
            "climate": "temperate",
            "terrain": "river_crossing",
            "status": "neutral"
        },
        {
            "name": "Арнор",
            "region": "eriador",
            "description": "Северное королевство дунэдайн; Аннумінас и Форност, распалось на Артэдайн, Кардолан и Рудаур.",
            "svg_path_data": "M976.2,557c-9,0-20-1-26-5s-27-11-31,1s-10,13-31,17s-21,3-35,3s-39.4-5.3-39.4-5.3l9.4-8.7c13-10,15-30,18-56 s-15-52-30-76s-28-47-12-69s15-25,23-48s-15-48-15-48l0.3,0.6c0,0,9-4,19-4s31-2,40-7c9-5,34-5,53-5s49-3,65-2s27,0,42,15 c15,15,9,5,19,25s12,24,4,44s-19,31-16,43s29,43,29,43s-26,1-31,24s-13,47-9,57c4,10,21,21,22,33s-1,18-1,18s-19-2-29-2 c-10,0-14.5,9.3-14.5,9.3L976.2,557z",
            "resource_wealth": 300,
            "strategic_value": 9,
            "population": 2000,
            "fortifications": 7,
            "trade_routes": ["fornost", "bree", "rivendell"],
            "special_resources": ["ancient_ruins", "strategic_position"],
            "climate": "temperate",
            "terrain": "hills_plains",
            "status": "contested"
        },
        {
            "name": "Форност",
            "region": "eriador",
            "description": "Форност Эраїн на Северных Холмах — поздняя столица Артэдайна, падшая в войне с Ангмаром.",
            "svg_path_data": "M1044.2,546.2c0,0,2-6,1-18s-18-23-22-33c-4-10,4-34,9-57s31-24,31-24l-0.4-0.9l0.4,0.9c0,0,22,3,45-1l10-3 c9,6,29,5,43,1s34,15,46,22s35,28,33,61s0,21,16,40s24,34,24,34l0.3-0.6c0,0-28,10-41,17s-32,16-38,12s-9,0-40,5s-50,5-64,3 s-13-13-21-26s-32-33-32-33L1044.2,546.2z",
            "resource_wealth": 250,
            "strategic_value": 8,
            "population": 1500,
            "fortifications": 6,
            "trade_routes": ["arnor", "angmar"],
            "special_resources": ["fortress", "strategic_hills"],
            "climate": "temperate",
            "terrain": "hills",
            "status": "contested"
        },
        {
            "name": "Троллистое плато",
            "region": "eriador",
            "description": "Дикие земли троллей к северу и востоку от Ривенделла (Эттенмоур и окрестности Троллистых холмов).",
            "svg_path_data": "M1144.6,392.1c7.7-4.9,34.9,3.5,56-3c29-9,39-9,62-10s76,45,90,53s44,18,60,15s50-10,73-13s57-3,60-3l0.9,0.4 c0,0,13,10-2,28s-15,18-28,24s-17,15-29,25c-12,10-39,25-42,36s-12,21-9,40c0,0-48,2-69-9s-38-21-52-18s-36,11-36,11s-8-15-24-34 s-18-7-16-40s-21-54-33-61s-32-26-46-22s-34,5-43-1c9.1-3,13.6-6.4,16-9c0.5-0.5,1.9-2.1,4-4 C1137.5,397.6,1140.8,394.6,1144.6,392.1z",
            "resource_wealth": 100,
            "strategic_value": 4,
            "population": 200,
            "fortifications": 1,
            "trade_routes": ["rivendell"],
            "special_resources": ["troll_caves", "wilderness"],
            "climate": "harsh",
            "terrain": "plateau",
            "status": "neutral"
        },
        {
            "name": "Долина Митлонд",
            "region": "lindon",
            "description": "Окрестности Митлонда (Серых Гаваней) у залива Лун; западные ворота эльфов в море.",
            "svg_path_data": "M561.4,469.1c0,12,15,37,23,59s34,17,59,14l19.5,1.7c-14.5,27.2-53.5,67.8-72.5,74.8s-40,59-53,77 s-69,31-93,27s-39,4-68,12s-46,3-59-1s-19-20-26-23s-36-7-44-11s-26-12-30-22s-18-15-25-22s4-14,6-20s-6-8-4-16s11-10,29-20 s17-15,14-35s6-24,13-32s6-18,6-29c0-11,18-4,28-11s12.5,4.6,12.5,4.6c0,6-3,41-3,50s11,22,11,34s7,15,22,46s63,28,63,28s5-16,5-25 s11-15,11-37s10-43,22-59s29-16,49-39c20-23,16-53,16-53s20.5-5.6,22.5-17.6s15-16,15-16S561.4,457.1,561.4,469.1z",
            "resource_wealth": 400,
            "strategic_value": 10,
            "population": 3000,
            "fortifications": 9,
            "trade_routes": ["grey_havens", "sea_routes"],
            "special_resources": ["harbor", "elven_craftsmanship", "sea_access"],
            "climate": "maritime",
            "terrain": "coastal_valley",
            "status": "active"
        },
        
        # Дополнительные территории (нужно добавить SVG path data)
        {
            "name": "Форлиндон",
            "region": "lindon",
            "description": "Северная часть Линдона, земли эльфов к северу от Серых Гаваней.",
            "svg_path_data": "",  # Нужно добавить из SVG
            "resource_wealth": 200,
            "strategic_value": 6,
            "population": 800,
            "fortifications": 4,
            "trade_routes": ["grey_havens"],
            "special_resources": ["elven_forests"],
            "climate": "temperate",
            "terrain": "forest",
            "status": "neutral"
        },
        {
            "name": "Харлиндон",
            "region": "lindon",
            "description": "Южная часть Линдона, земли эльфов к югу от Серых Гаваней.",
            "svg_path_data": "",  # Нужно добавить из SVG
            "resource_wealth": 180,
            "strategic_value": 5,
            "population": 600,
            "fortifications": 3,
            "trade_routes": ["grey_havens"],
            "special_resources": ["elven_forests"],
            "climate": "temperate",
            "terrain": "forest",
            "status": "neutral"
        },
        {
            "name": "Шир",
            "region": "eriador",
            "description": "Земли хоббитов, мирная сельская местность с холмами и фермами.",
            "svg_path_data": "",  # Нужно добавить из SVG
            "resource_wealth": 120,
            "strategic_value": 3,
            "population": 1500,
            "fortifications": 1,
            "trade_routes": ["bree"],
            "special_resources": ["agriculture", "peaceful"],
            "climate": "temperate",
            "terrain": "hills",
            "status": "neutral"
        },
        {
            "name": "Ривенделл (Имладрис)",
            "region": "eriador",
            "description": "Последний приют эльфов в Эриадоре, дом Эльронда.",
            "svg_path_data": "",  # Нужно добавить из SVG
            "resource_wealth": 350,
            "strategic_value": 9,
            "population": 1200,
            "fortifications": 8,
            "trade_routes": ["ford_of_bruinen", "misty_mountains"],
            "special_resources": ["elven_wisdom", "healing"],
            "climate": "temperate",
            "terrain": "valley",
            "status": "active"
        },
        {
            "name": "Минас Тирит",
            "region": "gondor",
            "description": "Столица Гондора, Город Королей, белый город на семи уровнях.",
            "svg_path_data": "",  # Нужно добавить из SVG
            "resource_wealth": 800,
            "strategic_value": 10,
            "population": 5000,
            "fortifications": 10,
            "trade_routes": ["osgiliath", "pelennor"],
            "special_resources": ["capital", "white_tower"],
            "climate": "temperate",
            "terrain": "city",
            "status": "active"
        },
        {
            "name": "Мордор",
            "region": "mordor",
            "description": "Земли Тьмы, владения Саурона, окруженные горами.",
            "svg_path_data": "",  # Нужно добавить из SVG
            "resource_wealth": 600,
            "strategic_value": 10,
            "population": 8000,
            "fortifications": 9,
            "trade_routes": ["black_gates"],
            "special_resources": ["dark_forces", "volcano"],
            "climate": "harsh",
            "terrain": "volcanic",
            "status": "contested"
        }
    ]
    
    try:
        print("🌱 Начинаем заполнение базы данных всеми территориями...")
        
        created_count = 0
        skipped_count = 0
        
        for territory_data in territories_data:
            # Проверяем, существует ли уже территория с таким именем
            existing = repo.get_by_name(territory_data["name"])
            if existing:
                print(f"⚠️ Территория '{territory_data['name']}' уже существует, пропускаем")
                skipped_count += 1
                continue
            
            # Пропускаем территории без SVG path data (временно)
            if not territory_data["svg_path_data"]:
                print(f"⚠️ Территория '{territory_data['name']}' без SVG path data, пропускаем")
                skipped_count += 1
                continue
            
            # Проверяем, существует ли уже территория с таким SVG path data
            existing_path = repo.get_by_svg_path_data(territory_data["svg_path_data"])
            if existing_path:
                print(f"⚠️ Территория с таким SVG path data уже существует, пропускаем")
                skipped_count += 1
                continue
            
            # Создаем территорию
            territory_create = TerritoryCreate(**territory_data)
            territory = repo.create(territory_create)
            print(f"✅ Создана территория: {territory.name} (ID: {territory.id})")
            created_count += 1
        
        print("🎉 Заполнение базы данных завершено!")
        print(f"📊 Статистика: создано {created_count}, пропущено {skipped_count}")
        
        # Показываем общую статистику
        stats = repo.get_territory_stats()
        print(f"📊 Общая статистика: всего территорий: {stats['total']}")
        
    except Exception as e:
        print(f"❌ Ошибка при заполнении базы данных: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_all_territories()
