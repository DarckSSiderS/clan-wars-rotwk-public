#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для тестирования API заданий
"""

import requests
import json

def test_quest_api():
    """Тестирование API заданий"""
    base_url = "http://localhost:8000"
    
    # Тестируем получение ежедневных заданий
    print("🔍 Тестирование API заданий...")
    
    try:
        # Получаем ежедневные задания
        response = requests.get(f"{base_url}/api/v1/quests/daily")
        print(f"📊 Статус ответа: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Получено {len(data)} ежедневных заданий")
            for quest in data:
                print(f"  - {quest['quest']['title']}: {quest['user_quest']['current_progress']}/{quest['quest']['target_value']}")
        else:
            print(f"❌ Ошибка: {response.text}")
            
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")

if __name__ == "__main__":
    test_quest_api() 