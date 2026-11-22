import requests
import json
from datetime import datetime

def test_quest_time():
    base_url = "http://localhost:3000/api/v1"
    
    # Данные для входа
    login_data = {
        "username": "Zira_aa",
        "password": "test123"
    }
    
    print("🔍 Тестирование времени до обновления заданий...")
    
    # 1. Входим в систему
    print("📝 Вход в систему...")
    try:
        login_response = requests.post(f"{base_url}/auth/login", data=login_data)
        
        if login_response.status_code != 200:
            print(f"❌ Ошибка входа: {login_response.status_code}")
            print(login_response.text)
            return
        
        # Получаем токен
        token_data = login_response.json()
        access_token = token_data.get("access_token")
        
        if not access_token:
            print("❌ Не удалось получить токен доступа")
            return
        
        print("✅ Успешный вход")
        
        # Заголовки для авторизованных запросов
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # 2. Тестируем ежедневные задания
        print("\n📅 Тестирование ежедневных заданий...")
        daily_response = requests.get(f"{base_url}/quests/daily?language=eng", headers=headers)
        
        print(f"📊 Статус ответа: {daily_response.status_code}")
        
        if daily_response.status_code == 200:
            daily_data = daily_response.json()
            print(f"✅ Получено {len(daily_data)} ежедневных заданий")
            for i, quest in enumerate(daily_data):
                print(f"\n  {i+1}. {quest['quest']['title']}")
                print(f"     Прогресс: {quest['user_quest']['current_progress']}/{quest['quest']['target_value']}")
                print(f"     Время до обновления: '{quest['quest'].get('time_until_reset', 'НЕТ ДАННЫХ')}'")
                print(f"     Завершено: {quest['user_quest']['is_completed']}")
                print(f"     Награда получена: {quest['user_quest'].get('is_claimed', False)}")
        else:
            print(f"❌ Ошибка: {daily_response.text}")
        
        # 3. Тестируем еженедельные задания
        print("\n📅 Тестирование еженедельных заданий...")
        weekly_response = requests.get(f"{base_url}/quests/weekly?language=eng", headers=headers)
        
        print(f"📊 Статус ответа: {weekly_response.status_code}")
        
        if weekly_response.status_code == 200:
            weekly_data = weekly_response.json()
            print(f"✅ Получено {len(weekly_data)} еженедельных заданий")
            for i, quest in enumerate(weekly_data):
                print(f"\n  {i+1}. {quest['quest']['title']}")
                print(f"     Прогресс: {quest['user_quest']['current_progress']}/{quest['quest']['target_value']}")
                print(f"     Время до обновления: '{quest['quest'].get('time_until_reset', 'НЕТ ДАННЫХ')}'")
                print(f"     Завершено: {quest['user_quest']['is_completed']}")
                print(f"     Награда получена: {quest['user_quest'].get('is_claimed', False)}")
        else:
            print(f"❌ Ошибка: {weekly_response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Не удалось подключиться к серверу. Убедитесь, что сервер запущен на порту 3000.")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    test_quest_time() 