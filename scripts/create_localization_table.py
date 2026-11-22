#!/usr/bin/env python3
"""
Скрипт для создания таблицы локализации
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import sys

# Параметры подключения к базе данных
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'clanwar_db',
    'user': 'clanwar_user',
    'password': 'clanwar_password'
}

def create_localization_table():
    """Создает таблицу локализации"""
    
    try:
        # Подключение к базе данных
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("Подключение к базе данных установлено")
        
        # Проверяем существование таблицы
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'localization'
            );
        """)
        
        if cursor.fetchone()['exists']:
            print("Таблица 'localization' уже существует!")
            return
        
        # Создаем таблицу
        cursor.execute("""
            CREATE TABLE localization (
                id SERIAL PRIMARY KEY,
                identifier VARCHAR(255) NOT NULL,
                ru TEXT NOT NULL,
                eng TEXT NOT NULL,
                webpage VARCHAR(100) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Создаем индексы
        cursor.execute("""
            CREATE INDEX idx_localization_identifier ON localization(identifier);
            CREATE INDEX idx_localization_webpage ON localization(webpage);
            CREATE INDEX idx_localization_identifier_webpage ON localization(identifier, webpage);
        """)
        
        # Подтверждаем изменения
        conn.commit()
        
        print("Таблица 'localization' успешно создана!")
        print("Созданы индексы для оптимизации запросов")
        
    except psycopg2.Error as e:
        print(f"Ошибка базы данных: {e}")
        if conn:
            conn.rollback()
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

if __name__ == "__main__":
    print("Создание таблицы локализации...")
    create_localization_table()
    print("Готово!") 