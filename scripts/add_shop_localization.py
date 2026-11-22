#!/usr/bin/env python3
"""
Скрипт для добавления локализационных данных для страницы магазина
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Конфигурация базы данных
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'clanwar_db'),
    'user': os.getenv('DB_USER', 'clanwar_user'),
    'password': os.getenv('DB_PASSWORD', 'clanwar_password')
}

# Данные для локализации магазина
SHOP_LOCALIZATION_DATA = [
    {
        'identifier': 'shop_title',
        'ru': 'Магазин украшений',
        'eng': 'Decoration Shop',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_subtitle',
        'ru': 'Украсьте свой профиль и карточки статистики уникальными предметами',
        'eng': 'Decorate your profile and statistics cards with unique items',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_loading',
        'ru': 'Загрузка...',
        'eng': 'Loading...',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_balance_title',
        'ru': 'Ваш баланс',
        'eng': 'Your Balance',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_balance_coins',
        'ru': 'монет',
        'eng': 'coins',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_balance_add',
        'ru': 'Пополнить баланс',
        'eng': 'Add Balance',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_categories_title',
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
    },
    {
        'identifier': 'shop_items_title',
        'ru': 'Доступные предметы',
        'eng': 'Available Items',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_no_items_title',
        'ru': 'Предметы не найдены',
        'eng': 'No Items Found',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_no_items_description',
        'ru': 'В магазине пока нет доступных предметов',
        'eng': 'No items available in the shop yet',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_item_no_description',
        'ru': 'Описание отсутствует',
        'eng': 'No description',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_item_buy',
        'ru': 'Купить',
        'eng': 'Buy',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_item_owned',
        'ru': 'Уже куплено',
        'eng': 'Already Owned',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_rarity_common',
        'ru': 'Обычный',
        'eng': 'Common',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_rarity_rare',
        'ru': 'Редкий',
        'eng': 'Rare',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_rarity_epic',
        'ru': 'Эпический',
        'eng': 'Epic',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_rarity_legendary',
        'ru': 'Легендарный',
        'eng': 'Legendary',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_inventory_title',
        'ru': 'Мои предметы',
        'eng': 'My Items',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_inventory_empty_title',
        'ru': 'Инвентарь пуст',
        'eng': 'Inventory Empty',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_inventory_empty_description',
        'ru': 'У вас пока нет купленных предметов',
        'eng': 'You don\'t have any purchased items yet',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_inventory_equipped',
        'ru': 'Экипировано',
        'eng': 'Equipped',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_inventory_equip',
        'ru': 'Экипировать',
        'eng': 'Equip',
        'webpage': 'shop'
    },
    {
        'identifier': 'shop_inventory_unequip',
        'ru': 'Снять',
        'eng': 'Unequip',
        'webpage': 'shop'
    }
]

def add_shop_localization():
    """Добавляет локализационные данные для страницы магазина"""
    print("Добавление локализационных данных для страницы магазина...")
    
    try:
        # Подключение к базе данных
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("Подключение к базе данных установлено")
        
        added_count = 0
        skipped_count = 0
        
        # Добавляем каждую запись
        for item in SHOP_LOCALIZATION_DATA:
            # Проверяем, существует ли уже запись
            cursor.execute(
                "SELECT id FROM localizations WHERE identifier = %s AND webpage = %s",
                (item['identifier'], item['webpage'])
            )
            
            existing_record = cursor.fetchone()
            
            if existing_record:
                print(f"Пропускаем существующую запись: {item['identifier']}")
                skipped_count += 1
            else:
                # Добавляем новую запись
                cursor.execute(
                    """
                    INSERT INTO localizations (identifier, ru, eng, webpage)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (item['identifier'], item['ru'], item['eng'], item['webpage'])
                )
                print(f"Добавлена запись: {item['identifier']}")
                added_count += 1
        
        # Подтверждаем изменения
        conn.commit()
        
        # Получаем общее количество записей для магазина
        cursor.execute("SELECT COUNT(*) as count FROM localizations WHERE webpage = 'shop'")
        total_count = cursor.fetchone()['count']
        
        print(f"\nРезультат:")
        print(f"- Добавлено записей: {added_count}")
        print(f"- Пропущено существующих: {skipped_count}")
        print(f"- Всего обработано: {added_count + skipped_count}")
        print(f"- Всего записей для магазина в базе: {total_count}")
        
    except Exception as e:
        print(f"Ошибка: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            print("Соединение с базой данных закрыто")
    
    print("Готово!")

if __name__ == "__main__":
    add_shop_localization() 