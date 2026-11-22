#!/usr/bin/env python3
"""
Скрипт для экспорта базы данных PostgreSQL
"""

import os
import subprocess
import sys
from datetime import datetime

def export_database():
    """Экспортирует базу данных PostgreSQL"""
    
    # Параметры подключения к базе данных
    DB_NAME = "clanwar_db"
    DB_USER = "clanwar_user"
    DB_PASSWORD = "clanwar_password"  # Пароль из конфигурации
    DB_HOST = "localhost"
    DB_PORT = "5432"
    
    # Создаем имя файла с текущей датой
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"clanwar_db_backup_{timestamp}.sql"
    
    # Команда для экспорта
    export_command = [
        "pg_dump",
        f"--host={DB_HOST}",
        f"--port={DB_PORT}",
        f"--username={DB_USER}",
        f"--dbname={DB_NAME}",
        "--verbose",
        "--clean",
        "--no-owner",
        "--no-privileges",
        f"--file={backup_file}"
    ]
    
    # Устанавливаем переменную окружения для пароля
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD
    
    try:
        print(f"🔄 Начинаем экспорт базы данных {DB_NAME}...")
        print(f"📁 Файл: {backup_file}")
        
        # Выполняем команду экспорта
        result = subprocess.run(
            export_command,
            env=env,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Экспорт базы данных завершен успешно!")
            print(f"📄 Файл сохранен: {backup_file}")
            
            # Показываем размер файла
            if os.path.exists(backup_file):
                size = os.path.getsize(backup_file)
                print(f"📊 Размер файла: {size / 1024 / 1024:.2f} MB")
        else:
            print("❌ Ошибка при экспорте базы данных:")
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            
    except FileNotFoundError:
        print("❌ pg_dump не найден. Убедитесь, что PostgreSQL установлен и pg_dump доступен в PATH")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    export_database() 