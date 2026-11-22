import requests
import json

def test_quest_api():
    base_url = "http://localhost:3000/api/v1"
    
    # Данные для входа
    login_data = {
        "username": "Zira_aa",
        "password": "test123"
    }
    
    print("🔍 Тестирование API заданий с аутентификацией...")
    
    # 1. Входим в систему
    print("📝 Вход в систему...")
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
            print(f"  {i+1}. {quest['quest']['title']} - {quest['user_quest']['current_progress']}/{quest['quest']['target_value']}")
            if 'time_until_reset' in quest['quest']:
                print(f"     Время до обновления: {quest['quest']['time_until_reset']}")
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
            print(f"  {i+1}. {quest['quest']['title']} - {quest['user_quest']['current_progress']}/{quest['quest']['target_value']}")
            if 'time_until_reset' in quest['quest']:
                print(f"     Время до обновления: {quest['quest']['time_until_reset']}")
    else:
        print(f"❌ Ошибка: {weekly_response.text}")
    
    # 4. Тестируем обновление прогресса
    print("\n🔄 Тестирование обновления прогресса...")
    progress_response = requests.post(f"{base_url}/quests/update-progress", headers=headers)
    
    print(f"📊 Статус ответа: {progress_response.status_code}")
    
    if progress_response.status_code == 200:
        progress_data = progress_response.json()
        print(f"✅ {progress_data.get('message', 'Прогресс обновлен')}")
        if 'stats' in progress_data:
            stats = progress_data['stats']
            print(f"   Статистика: {stats['total_matches']} матчей, {stats['wins']} побед")
    else:
        print(f"❌ Ошибка: {progress_response.text}")

if __name__ == "__main__":
    test_quest_api() 