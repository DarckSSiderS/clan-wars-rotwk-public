import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import json

def test_quest_api_moscow_time():
    """Тестирование API заданий с московским временем"""
    
    print("🕐 Тестирование API заданий с московским временем")
    print("=" * 60)
    
    # Базовый URL
    base_url = "http://localhost:3000"
    
    # Данные для входа
    login_data = {
        "username": "Zira_aa",
        "password": "test123"
    }
    
    try:
        # Входим в систему
        print("🔐 Вход в систему...")
        login_response = requests.post(f"{base_url}/api/v1/auth/login", json=login_data)
        
        if login_response.status_code != 200:
            print(f"❌ Ошибка входа: {login_response.status_code}")
            return
        
        token_data = login_response.json()
        access_token = token_data.get("access_token")
        
        if not access_token:
            print("❌ Не получен токен доступа")
            return
        
        print("✅ Успешный вход")
        
        # Заголовки для авторизованных запросов
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Получаем ежедневные задания
        print("\n📅 Получение ежедневных заданий...")
        daily_response = requests.get(f"{base_url}/api/v1/quests/daily?language=ru", headers=headers)
        
        if daily_response.status_code == 200:
            daily_quests = daily_response.json()
            print(f"✅ Получено {len(daily_quests)} ежедневных заданий")
            
            for i, quest_data in enumerate(daily_quests, 1):
                quest = quest_data["quest"]
                user_quest = quest_data["user_quest"]
                
                print(f"\n📋 Задание {i}:")
                print(f"   Название: {quest['title']}")
                print(f"   Описание: {quest['description']}")
                print(f"   Прогресс: {user_quest['current_progress']} / {quest['target_value']}")
                print(f"   Статус: {'Завершено' if user_quest['is_completed'] else 'В процессе'}")
                print(f"   Награда получена: {'Да' if user_quest['is_claimed'] else 'Нет'}")
                print(f"   Время до сброса: {quest['time_until_reset']}")
                print(f"   Истекает: {user_quest['expires_at']}")
        else:
            print(f"❌ Ошибка получения ежедневных заданий: {daily_response.status_code}")
        
        # Получаем еженедельные задания
        print("\n📅 Получение еженедельных заданий...")
        weekly_response = requests.get(f"{base_url}/api/v1/quests/weekly?language=ru", headers=headers)
        
        if weekly_response.status_code == 200:
            weekly_quests = weekly_response.json()
            print(f"✅ Получено {len(weekly_quests)} еженедельных заданий")
            
            for i, quest_data in enumerate(weekly_quests, 1):
                quest = quest_data["quest"]
                user_quest = quest_data["user_quest"]
                
                print(f"\n📋 Задание {i}:")
                print(f"   Название: {quest['title']}")
                print(f"   Описание: {quest['description']}")
                print(f"   Прогресс: {user_quest['current_progress']} / {quest['target_value']}")
                print(f"   Статус: {'Завершено' if user_quest['is_completed'] else 'В процессе'}")
                print(f"   Награда получена: {'Да' if user_quest['is_claimed'] else 'Нет'}")
                print(f"   Время до сброса: {quest['time_until_reset']}")
                print(f"   Истекает: {user_quest['expires_at']}")
        else:
            print(f"❌ Ошибка получения еженедельных заданий: {weekly_response.status_code}")
        
        print("\n✅ Тест завершен!")
        
    except requests.exceptions.ConnectionError:
        print("❌ Ошибка подключения к серверу. Убедитесь, что сервер запущен.")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    test_quest_api_moscow_time() 