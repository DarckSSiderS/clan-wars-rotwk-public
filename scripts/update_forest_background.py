#!/usr/bin/env python3
"""
Скрипт для обновления CSS класса лесного фона профиля
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

def update_forest_background():
    """Обновляет CSS класс лесного фона профиля"""
    print("Обновление CSS класса лесного фона профиля...")
    
    try:
        # Подключение к базе данных
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("Подключение к базе данных установлено")
        
        # Обновляем товар "Лесной фон профиля"
        cursor.execute(
            """
            UPDATE shop_items 
            SET css_class = 'anime-background'
            WHERE name = 'Лесной фон профиля'
            """
        )
        
        updated_count = cursor.rowcount
        print(f"Обновлено записей: {updated_count}")
        
        # Подтверждаем изменения
        conn.commit()
        
        # Проверяем результат
        cursor.execute(
            "SELECT name, css_class FROM shop_items WHERE name = 'Лесной фон профиля'"
        )
        result = cursor.fetchone()
        
        if result:
            print(f"Результат обновления:")
            print(f"- Название: {result['name']}")
            print(f"- CSS класс: {result['css_class']}")
        else:
            print("Товар не найден")
        
    except Exception as e:
        print(f"Ошибка: {e}")
        if conn: conn.rollback()
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
        print("Соединение с базой данных закрыто")
    
    print("Готово!")

if __name__ == "__main__":
    update_forest_background() 