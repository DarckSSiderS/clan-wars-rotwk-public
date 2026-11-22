#!/usr/bin/env python3
"""
Скрипт для добавления локализации для кнопки категорий магазина
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_db
from app.repositories.localization_repository import LocalizationRepository

def add_shop_categories_localization():
    """Добавляет локализацию для кнопки категорий магазина"""
    
    db = next(get_db())
    repo = LocalizationRepository(db)
    
    # Ключи для локализации
    localization_data = [
        {
            'identifier': 'shop_categories_button',
            'ru': 'Категории',
            'eng': 'Categories',
            'webpage': 'shop'
        },
        {
            'identifier': 'shop_category_all',
            'ru': 'Все',
            'eng': 'All',
            'webpage': 'shop'
        },
        {
            'identifier': 'shop_category_profile_frame',
            'ru': 'Рамки профиля',
            'eng': 'Profile Frames',
            'webpage': 'shop'
        },
        {
            'identifier': 'shop_category_stat_card_style',
            'ru': 'Стили карточек',
            'eng': 'Card Styles',
            'webpage': 'shop'
        },
        {
            'identifier': 'shop_category_avatar_frame',
            'ru': 'Рамки аватара',
            'eng': 'Avatar Frames',
            'webpage': 'shop'
        },
        {
            'identifier': 'shop_category_profile_background',
            'ru': 'Фоны профиля',
            'eng': 'Profile Backgrounds',
            'webpage': 'shop'
        }
    ]
    
    print("🔄 Добавление локализации для кнопки категорий магазина...")
    
    for item in localization_data:
        try:
            # Проверяем, существует ли уже такой ключ
            existing = repo.get_by_identifier(item['identifier'])
            if existing:
                print(f"⚠️  Ключ '{item['identifier']}' уже существует, пропускаем...")
                continue
            
            # Добавляем новую локализацию
            repo.create(
                identifier=item['identifier'],
                ru=item['ru'],
                eng=item['eng'],
                webpage=item['webpage']
            )
            print(f"✅ Добавлен ключ: {item['identifier']} - {item['ru']}")
            
        except Exception as e:
            print(f"❌ Ошибка при добавлении локализации: {e}")
    
    print("🎉 Локализация для кнопки категорий добавлена!")

if __name__ == "__main__":
    add_shop_categories_localization() 