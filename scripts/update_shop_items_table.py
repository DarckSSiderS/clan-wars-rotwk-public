#!/usr/bin/env python3
"""
Скрипт для добавления поля is_available в таблицу shop_items
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

def update_shop_items_table():
    """Добавляет поле is_available в таблицу shop_items"""
    print("Добавление поля is_available в таблицу shop_items...")
    
    try:
        # Подключение к базе данных
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("Подключение к базе данных установлено")
        
        # Проверяем, существует ли уже поле is_available
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'shop_items' AND column_name = 'is_available'
        """)
        
        existing_column = cursor.fetchone()
        
        if existing_column:
            print("Поле is_available уже существует")
        else:
            # Добавляем поле is_available
            cursor.execute("""
                ALTER TABLE shop_items 
                ADD COLUMN is_available BOOLEAN DEFAULT TRUE
            """)
            print("Поле is_available добавлено")
        
        # Обновляем существующие записи, устанавливая is_available = TRUE
        cursor.execute("""
            UPDATE shop_items 
            SET is_available = TRUE 
            WHERE is_available IS NULL
        """)
        
        updated_count = cursor.rowcount
        print(f"Обновлено записей: {updated_count}")
        
        # Подтверждаем изменения
        conn.commit()
        
        # Проверяем результат
        cursor.execute("SELECT COUNT(*) as count FROM shop_items WHERE is_available = TRUE")
        available_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM shop_items")
        total_count = cursor.fetchone()['count']
        
        print(f"\nРезультат:")
        print(f"- Всего товаров: {total_count}")
        print(f"- Доступных товаров: {available_count}")
        
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
    update_shop_items_table() 