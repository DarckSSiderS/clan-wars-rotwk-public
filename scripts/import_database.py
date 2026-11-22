#!/usr/bin/env python3
"""
Скрипт для импорта базы данных PostgreSQL на Linux
"""

import os
import subprocess
import sys
import glob

def import_database():
    """Импортирует базу данных PostgreSQL"""
    
    # Параметры подключения к базе данных
    DB_NAME = "clanwar_db"
    DB_USER = "clanwar_user"
    DB_PASSWORD = "clanwar_password"  # Пароль из конфигурации
    DB_HOST = "localhost"
    DB_PORT = "5432"
    
    # Ищем файл бэкапа
    backup_files = glob.glob("clanwar_db_backup_*.sql")
    
    if not backup_files:
        print("❌ Файл бэкапа не найден. Убедитесь, что файл clanwar_db_backup_*.sql находится в текущей директории")
        return
    
    # Берем самый новый файл
    backup_file = max(backup_files, key=os.path.getctime)
    print(f"📁 Найден файл бэкапа: {backup_file}")
    
    # Команда для импорта
    import_command = [
        "psql",
        f"--host={DB_HOST}",
        f"--port={DB_PORT}",
        f"--username={DB_USER}",
        f"--dbname={DB_NAME}",
        "--verbose",
        f"--file={backup_file}"
    ]
    
    # Устанавливаем переменную окружения для пароля
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD
    
    try:
        print(f"🔄 Начинаем импорт базы данных {DB_NAME}...")
        print(f"📁 Файл: {backup_file}")
        
        # Выполняем команду импорта
        result = subprocess.run(
            import_command,
            env=env,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Импорт базы данных завершен успешно!")
            print("🎉 База данных готова к использованию!")
        else:
            print("❌ Ошибка при импорте базы данных:")
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            
    except FileNotFoundError:
        print("❌ psql не найден. Убедитесь, что PostgreSQL установлен и psql доступен в PATH")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

def create_database():
    """Создает базу данных если она не существует"""
    
    DB_NAME = "clanwar_db"
    DB_USER = "postgres"
    DB_PASSWORD = "your_password"  # Замените на ваш пароль
    DB_HOST = "localhost"
    DB_PORT = "5432"
    
    # Команда для создания базы данных
    create_command = [
        "createdb",
        f"--host={DB_HOST}",
        f"--port={DB_PORT}",
        f"--username={DB_USER}",
        DB_NAME
    ]
    
    # Устанавливаем переменную окружения для пароля
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD
    
    try:
        print(f"🔄 Создаем базу данных {DB_NAME}...")
        
        result = subprocess.run(
            create_command,
            env=env,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"✅ База данных {DB_NAME} создана успешно!")
        else:
            print(f"⚠️ База данных {DB_NAME} уже существует или произошла ошибка:")
            print(f"STDERR: {result.stderr}")
            
    except FileNotFoundError:
        print("❌ createdb не найден. Убедитесь, что PostgreSQL установлен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    print("🚀 Скрипт импорта базы данных PostgreSQL")
    print("=" * 50)
    
    # Сначала создаем базу данных
    create_database()
    print()
    
    # Затем импортируем данные
    import_database() 