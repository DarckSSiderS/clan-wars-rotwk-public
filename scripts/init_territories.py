#!/usr/bin/env python3
"""
Скрипт для инициализации территорий на карте
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from database import engine, get_db
from models import Territory
from crud import create_territory

def init_territories():
    """Инициализирует территории на карте"""
    
    # Координаты территорий (примерные, основанные на карте)
    territories_data = [
        {
            "name": "Рохан",
            "x": 500,
            "y": 800,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Гондор",
            "x": 800,
            "y": 1000,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Мордор",
            "x": 1200,
            "y": 1200,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Изенгард",
            "x": 400,
            "y": 600,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Лотлориен",
            "x": 900,
            "y": 700,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Ривенделл",
            "x": 600,
            "y": 400,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Эсгарот",
            "x": 1100,
            "y": 500,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Дейл",
            "x": 1300,
            "y": 400,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Железные Холмы",
            "x": 1400,
            "y": 300,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Одинокая Гора",
            "x": 1200,
            "y": 300,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Минас Тирит",
            "x": 900,
            "y": 1100,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Минас Моргул",
            "x": 1100,
            "y": 1100,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Барад-дур",
            "x": 1300,
            "y": 1300,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Хельмова Падь",
            "x": 300,
            "y": 900,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Эдорас",
            "x": 600,
            "y": 900,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Дол Гулдур",
            "x": 1000,
            "y": 800,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Мория",
            "x": 700,
            "y": 600,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Лесной Край",
            "x": 800,
            "y": 500,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Шир",
            "x": 200,
            "y": 500,
            "is_neutral": True,
            "capture_requirement": 25
        },
        {
            "name": "Бри",
            "x": 300,
            "y": 400,
            "is_neutral": True,
            "capture_requirement": 25
        }
    ]
    
    db = next(get_db())
    
    try:
        # Проверяем, есть ли уже территории
        existing_territories = db.query(Territory).count()
        if existing_territories > 0:
            print(f"В базе данных уже есть {existing_territories} территорий. Пропускаем инициализацию.")
            return
        
        # Создаем территории
        for territory_data in territories_data:
            territory = create_territory(db, territory_data)
            print(f"Создана территория: {territory.name} (ID: {territory.id})")
        
        print(f"Успешно создано {len(territories_data)} территорий!")
        
    except Exception as e:
        print(f"Ошибка при создании территорий: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("Инициализация территорий...")
    init_territories()
    print("Готово!") 