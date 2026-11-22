import requests
import json

def test_localization_api():
    base_url = "http://localhost:8000"
    
    print("=== Тестирование API локализации ===")
    
    # Тест 1: Получить все записи локализации
    print("\n1. Получение всех записей локализации:")
    response = requests.get(f"{base_url}/api/v1/localization/")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Количество записей: {len(data)}")
        if data:
            print(f"Первая запись: {data[0]}")
    
    # Тест 2: Получить тексты для главной страницы на русском
    print("\n2. Получение текстов для главной страницы (RU):")
    response = requests.get(f"{base_url}/api/v1/localization/webpage/homepage/texts", params={"language": "ru"})
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Данные: {json.dumps(data, ensure_ascii=False, indent=2)}")
    
    # Тест 3: Получить тексты для главной страницы на английском
    print("\n3. Получение текстов для главной страницы (EN):")
    response = requests.get(f"{base_url}/api/v1/localization/webpage/homepage/texts", params={"language": "eng"})
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Данные: {json.dumps(data, ensure_ascii=False, indent=2)}")
    
    # Тест 4: Получить конкретный текст
    print("\n4. Получение конкретного текста:")
    response = requests.get(f"{base_url}/api/v1/localization/text/homepage_welcome_title", params={"language": "ru"})
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Данные: {json.dumps(data, ensure_ascii=False, indent=2)}")

if __name__ == "__main__":
    test_localization_api() 