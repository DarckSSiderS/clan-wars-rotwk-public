#!/usr/bin/env python3
"""
Скрипт для добавления тестовых товаров в магазин
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Конфигурация базы данных
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'clanwar_db'),
    'user': os.getenv('DB_USER', 'clanwar_user'),
    'password': os.getenv('DB_PASSWORD', 'clanwar_password')
}

# Тестовые товары для магазина
SHOP_ITEMS_DATA = [
    {
        'name': 'Золотая рамка профиля',
        'description': 'Элегантная золотая рамка для вашего профиля',
        'price': 500,
        'item_type': 'profile_frame',
        'rarity': 'rare',
        'image_url': '/icons/sauronwb.png',
        'css_class': 'gold-frame',
        'is_active': True
    },
    {
        'name': 'Огненная рамка аватара',
        'description': 'Рамка аватара с эффектом огня',
        'price': 750,
        'item_type': 'avatar_frame',
        'rarity': 'epic',
        'image_url': '/icons/sauronwb.png',
        'css_class': 'fire-frame',
        'is_active': True
    },
    {
        'name': 'Неоновый стиль карточек',
        'description': 'Стиль карточек с неоновым свечением',
        'price': 1000,
        'item_type': 'stat_card_style',
        'rarity': 'legendary',
        'image_url': '/icons/axeswb.png',
        'css_class': 'neon-style',
        'is_active': True
    },
    {
        'name': 'Космический фон профиля',
        'description': 'Красивый космический фон для профиля',
        'price': 800,
        'item_type': 'profile_background',
        'rarity': 'epic',
        'image_url': '/icons/towerwb.png',
        'css_class': 'space-bg',
        'is_active': True
    },
    {
        'name': 'Серебряная рамка профиля',
        'description': 'Стильная серебряная рамка',
        'price': 300,
        'item_type': 'profile_frame',
        'rarity': 'common',
        'image_url': '/icons/profilewb.png',
        'css_class': 'silver-frame',
        'is_active': True
    },
    {
        'name': 'Ледяная рамка аватара',
        'description': 'Рамка аватара с ледяным эффектом',
        'price': 600,
        'item_type': 'avatar_frame',
        'rarity': 'rare',
        'image_url': '/icons/towerwb.png',
        'css_class': 'ice-frame',
        'is_active': True
    },
    {
        'name': 'Классический стиль карточек',
        'description': 'Классический стиль для карточек статистики',
        'price': 400,
        'item_type': 'stat_card_style',
        'rarity': 'common',
        'image_url': '/icons/axeswb.png',
        'css_class': 'classic-style',
        'is_active': True
    },
    {
        'name': 'Лесной фон профиля',
        'description': 'Успокаивающий лесной фон',
        'price': 450,
        'item_type': 'profile_background',
        'rarity': 'rare',
        'image_url': '/icons/vswb.png',
        'css_class': 'anime-background',
        'is_active': True
    },
    {
        'name': 'Платиновая рамка профиля',
        'description': 'Эксклюзивная платиновая рамка',
        'price': 1200,
        'item_type': 'profile_frame',
        'rarity': 'legendary',
        'image_url': '/icons/sauronwb.png',
        'css_class': 'platinum-frame',
        'is_active': True
    },
    {
        'name': 'Радужная рамка аватара',
        'description': 'Яркая радужная рамка аватара',
        'price': 900,
        'item_type': 'avatar_frame',
        'rarity': 'epic',
        'image_url': '/icons/sauronwb.png',
        'css_class': 'rainbow-frame',
        'is_active': True
    }
]

def add_shop_items():
    """Добавляет тестовые товары в магазин"""
    print("Добавление тестовых товаров в магазин...")
    
    try:
        # Подключение к базе данных
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("Подключение к базе данных установлено")
        
        added_count = 0
        skipped_count = 0
        
        # Добавляем каждый товар
        for item in SHOP_ITEMS_DATA:
            # Проверяем, существует ли уже товар с таким именем
            cursor.execute(
                "SELECT id FROM shop_items WHERE name = %s",
                (item['name'],)
            )
            
            existing_record = cursor.fetchone()
            
            if existing_record:
                print(f"Пропускаем существующий товар: {item['name']}")
                skipped_count += 1
            else:
                # Добавляем новый товар
                cursor.execute(
                    """
                    INSERT INTO shop_items (name, description, price, item_type, rarity, image_url, css_class, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        item['name'],
                        item['description'],
                        item['price'],
                        item['item_type'],
                        item['rarity'],
                        item['image_url'],
                        item['css_class'],
                        item['is_active']
                    )
                )
                print(f"Добавлен товар: {item['name']} ({item['price']} монет)")
                added_count += 1
        
        # Подтверждаем изменения
        conn.commit()
        
        # Получаем общее количество товаров
        cursor.execute("SELECT COUNT(*) as count FROM shop_items")
        total_count = cursor.fetchone()['count']
        
        print(f"\nРезультат:")
        print(f"- Добавлено товаров: {added_count}")
        print(f"- Пропущено существующих: {skipped_count}")
        print(f"- Всего обработано: {added_count + skipped_count}")
        print(f"- Всего товаров в магазине: {total_count}")
        
    except Exception as e:
        print(f"Ошибка: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            print("Соединение с базой данных закрыто")
    
    print("Готово!")

if __name__ == "__main__":
    add_shop_items() 