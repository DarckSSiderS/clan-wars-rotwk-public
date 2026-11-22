#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестирование автоматического обновления заданий через API
"""

import requests
import json

def test_quest_api_update():
    print("=== Тестирование автоматического обновления заданий ===\n")
    
    # Базовый URL API
    base_url = "http://localhost:3000"
    
    # Данные для входа Alotes1
    login_data = {
        "username": "Alotes1",
        "password": "password123"
    }
    
    try:
        # Входим в систему
        print("🔐 Вход в систему...")
        login_response = requests.post(f"{base_url}/api/v1/auth/login", json=login_data)
        
        if login_response.status_code != 200:
            print(f"❌ Ошибка входа: {login_response.status_code}")
            print(login_response.text)
            return
        
        token = login_response.json()["access_token"]
        print("✅ Успешный вход")
        
        # Получаем ежедневные задания (должно автоматически обновить прогресс)
        print("\n📋 Получение ежедневных заданий...")
        headers = {"Authorization": f"Bearer {token}"}
        daily_response = requests.get(f"{base_url}/api/v1/quests/daily?language=ru", headers=headers)
        
        if daily_response.status_code != 200:
            print(f"❌ Ошибка получения ежедневных заданий: {daily_response.status_code}")
            print(daily_response.text)
            return
        
        daily_quests = daily_response.json()
        print(f"✅ Получено {len(daily_quests)} ежедневных заданий")
        
        # Показываем прогресс
        for quest in daily_quests:
            print(f"  🎯 {quest['title']}: {quest['current_progress']}/{quest['target_value']}")
        
        # Получаем еженедельные задания
        print("\n📋 Получение еженедельных заданий...")
        weekly_response = requests.get(f"{base_url}/api/v1/quests/weekly?language=ru", headers=headers)
        
        if weekly_response.status_code != 200:
            print(f"❌ Ошибка получения еженедельных заданий: {weekly_response.status_code}")
            print(weekly_response.text)
            return
        
        weekly_quests = weekly_response.json()
        print(f"✅ Получено {len(weekly_quests)} еженедельных заданий")
        
        # Показываем прогресс
        for quest in weekly_quests:
            print(f"  🎯 {quest['title']}: {quest['current_progress']}/{quest['target_value']}")
        
        print("\n✅ Тестирование завершено!")
        
    except requests.exceptions.ConnectionError:
        print("❌ Не удалось подключиться к серверу. Убедитесь, что сервер запущен на http://localhost:3000")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == '__main__':
    test_quest_api_update() 