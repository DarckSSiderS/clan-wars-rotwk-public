import requests
import os

def test_avatar_upload():
    # URL сервера
    base_url = "http://localhost:3000"
    
    # Данные для авторизации (замените на реальные)
    login_data = {
        "username": "Zira_aa",  # Замените на реального пользователя
        "password": "password123"  # Замените на реальный пароль
    }
    
    try:
        # Авторизация
        print("Авторизация...")
        login_response = requests.post(f"{base_url}/api/v1/auth/login", data=login_data)
        
        if login_response.status_code != 200:
            print(f"Ошибка авторизации: {login_response.status_code}")
            print(login_response.text)
            return
        
        # Получаем токен
        token = login_response.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        
        print("Токен получен успешно")
        
        # Получаем информацию о пользователе
        user_response = requests.get(f"{base_url}/api/v1/users/me", headers=headers)
        if user_response.status_code == 200:
            user_data = user_response.json()
            print(f"Пользователь: {user_data['username']}")
            
            # Получаем клан пользователя
            clan_response = requests.get(f"{base_url}/api/v1/clans/my", headers=headers)
            if clan_response.status_code == 200:
                clan_data = clan_response.json()
                clan_id = clan_data['id']
                print(f"Клан: {clan_data['name']} (ID: {clan_id})")
                
                # Проверяем, является ли пользователь лидером
                if clan_data['leader_id'] == user_data['id']:
                    print("Пользователь является лидером клана")
                    
                    # Создаем тестовое изображение
                    test_image_path = "test_avatar.png"
                    if not os.path.exists(test_image_path):
                        # Создаем простое тестовое изображение
                        from PIL import Image, ImageDraw
        
                        # Создаем изображение 100x100 пикселей
                        img = Image.new('RGB', (100, 100), color='red')
                        draw = ImageDraw.Draw(img)
                        draw.text((10, 40), "TEST", fill='white')
                        img.save(test_image_path)
                        print(f"Создано тестовое изображение: {test_image_path}")
                    
                    # Загружаем аватар
                    print("Загружаем аватар...")
                    with open(test_image_path, 'rb') as f:
                        files = {'avatar': f}
                        upload_response = requests.post(
                            f"{base_url}/api/v1/clans/{clan_id}/avatar",
                            files=files,
                            headers=headers
                        )
                    
                    if upload_response.status_code == 200:
                        result = upload_response.json()
                        print(f"Аватар загружен успешно!")
                        print(f"URL: {result['avatar_url']}")
                        print(f"Сообщение: {result['message']}")
                        
                        # Проверяем, что файл существует
                        file_path = f"static{result['avatar_url']}"
                        if os.path.exists(file_path):
                            print(f"Файл существует: {file_path}")
                            print(f"Размер файла: {os.path.getsize(file_path)} байт")
                        else:
                            print(f"Файл не найден: {file_path}")
                    else:
                        print(f"Ошибка загрузки аватара: {upload_response.status_code}")
                        print(upload_response.text)
                else:
                    print("Пользователь не является лидером клана")
            else:
                print(f"Ошибка получения клана: {clan_response.status_code}")
        else:
            print(f"Ошибка получения данных пользователя: {user_response.status_code}")
            
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    test_avatar_upload() 