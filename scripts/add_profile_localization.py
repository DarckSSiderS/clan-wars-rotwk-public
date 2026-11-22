#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Данные для подключения к базе данных
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'clanwar_db'),
    'user': os.getenv('DB_USER', 'clanwar_user'),
    'password': os.getenv('DB_PASSWORD', 'clanwar_password')
}

# Локализационные данные для страницы профиля
PROFILE_LOCALIZATION_DATA = [
    # Новые ключи для улучшенного профиля
    {
        'identifier': 'profile_you',
        'ru': 'Вы',
        'eng': 'You',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_unknown_clan',
        'ru': 'Неизвестный клан',
        'eng': 'Unknown Clan',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_unknown',
        'ru': 'Неизвестно',
        'eng': 'Unknown',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_no_description',
        'ru': 'Описание отсутствует',
        'eng': 'No description',
        'webpage': 'profile'
    },
    # Существующие ключи
    {
        'identifier': 'profile_level',
        'ru': 'Уровень',
        'eng': 'Level',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_experience',
        'ru': 'опыта',
        'eng': 'experience',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_user_info_title',
        'ru': 'Информация о пользователе',
        'eng': 'User Information',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_user_info_username',
        'ru': 'Имя пользователя',
        'eng': 'Username',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_user_info_email',
        'ru': 'Email',
        'eng': 'Email',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_user_info_created',
        'ru': 'Дата регистрации',
        'eng': 'Registration Date',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_user_info_status',
        'ru': 'Статус',
        'eng': 'Status',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_user_info_status_active',
        'ru': 'Активен',
        'eng': 'Active',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_user_info_balance',
        'ru': 'Баланс',
        'eng': 'Balance',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_clan_info_title',
        'ru': 'Информация о клане',
        'eng': 'Clan Information',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_clan_info_view',
        'ru': 'Просмотр',
        'eng': 'View',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_clan_info_no_clan_title',
        'ru': 'Вы не состоите в клане',
        'eng': 'You are not in a clan',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_clan_info_no_clan_description',
        'ru': 'Создайте свой клан или присоединитесь к существующему',
        'eng': 'Create your own clan or join an existing one',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_clan_info_create_clan',
        'ru': 'Создать клан',
        'eng': 'Create Clan',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_tab_statistics',
        'ru': 'Статистика',
        'eng': 'Statistics',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_tab_inventory',
        'ru': 'Инвентарь',
        'eng': 'Inventory',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_tab_achievements',
        'ru': 'Достижения',
        'eng': 'Achievements',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_statistics_overall',
        'ru': 'Общая статистика',
        'eng': 'Overall Statistics',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_statistics_total_matches',
        'ru': 'Всего матчей',
        'eng': 'Total Matches',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_statistics_wins',
        'ru': 'Победы',
        'eng': 'Wins',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_statistics_losses',
        'ru': 'Поражения',
        'eng': 'Losses',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_statistics_no_data_title',
        'ru': 'Нет данных о матчах',
        'eng': 'No Match Data',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_statistics_no_data_description',
        'ru': 'У вас пока нет сыгранных матчей в базе данных',
        'eng': 'You don\'t have any played matches in the database yet',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_inventory_empty_title',
        'ru': 'Инвентарь пуст',
        'eng': 'Inventory Empty',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_inventory_empty_description',
        'ru': 'У вас пока нет купленных предметов',
        'eng': 'You don\'t have any purchased items yet',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_inventory_go_to_shop',
        'ru': 'Перейти в магазин',
        'eng': 'Go to Shop',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_inventory_equipped',
        'ru': 'Экипировано',
        'eng': 'Equipped',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_inventory_equip',
        'ru': 'Экипировать',
        'eng': 'Equip',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_inventory_unequip',
        'ru': 'Снять',
        'eng': 'Unequip',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_invites_title',
        'ru': 'Приглашения в кланы',
        'eng': 'Clan Invites',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_invites_no_invites_title',
        'ru': 'Приглашений нет',
        'eng': 'No Invites',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_invites_no_invites_description',
        'ru': 'У вас пока нет приглашений в кланы',
        'eng': 'You don\'t have any clan invites yet',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_invites_from',
        'ru': 'Приглашение от',
        'eng': 'Invitation from',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_invites_accept',
        'ru': 'Принять',
        'eng': 'Accept',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_invites_decline',
        'ru': 'Отклонить',
        'eng': 'Decline',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_loading',
        'ru': 'Загрузка...',
        'eng': 'Loading...',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_loading_statistics',
        'ru': 'Загрузка статистики...',
        'eng': 'Loading statistics...',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_loading_achievements',
        'ru': 'Загрузка достижений...',
        'eng': 'Loading achievements...',
        'webpage': 'profile'
    },
    {
        'identifier': 'profile_achievements_title',
        'ru': 'Достижения',
        'eng': 'Achievements',
        'webpage': 'profile'
    },
         {
         'identifier': 'profile_achievements_in_development',
         'ru': 'Система достижений в разработке...',
         'eng': 'Achievement system in development...',
         'webpage': 'profile'
     },
     {
         'identifier': 'profile_clan_info_no_clan_title_other',
         'ru': 'Пользователь не состоит в клане',
         'eng': 'User is not in a clan',
         'webpage': 'profile'
     },
     {
         'identifier': 'profile_clan_info_no_clan_description_other',
         'ru': 'Этот пользователь пока не присоединился ни к одному клану',
         'eng': 'This user has not joined any clan yet',
         'webpage': 'profile'
     },
     {
         'identifier': 'profile_equipped_items',
         'ru': 'Экипированные предметы',
         'eng': 'Equipped Items',
         'webpage': 'profile'
     }
]

def add_localization_data():
    """Добавляет локализационные данные для страницы профиля"""
    print("Добавление локализационных данных для страницы профиля...")
    
    try:
        # Подключаемся к базе данных
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("Подключение к базе данных установлено")
        
        added_count = 0
        skipped_count = 0
        
        for data in PROFILE_LOCALIZATION_DATA:
            # Проверяем, существует ли уже запись
            cursor.execute("""
                SELECT id FROM localizations 
                WHERE identifier = %s AND webpage = %s
            """, (data['identifier'], data['webpage']))
            
            existing = cursor.fetchone()
            
            if existing:
                print(f"Пропускаем существующую запись: {data['identifier']}")
                skipped_count += 1
            else:
                # Добавляем новую запись
                cursor.execute("""
                    INSERT INTO localizations (identifier, ru, eng, webpage)
                    VALUES (%s, %s, %s, %s)
                """, (
                    data['identifier'],
                    data['ru'],
                    data['eng'],
                    data['webpage']
                ))
                
                print(f"Добавлена запись: {data['identifier']}")
                added_count += 1
        
        # Подтверждаем изменения
        conn.commit()
        
        # Получаем общее количество записей для профиля
        cursor.execute("""
            SELECT COUNT(*) as total FROM localizations WHERE webpage = 'profile'
        """)
        total_count = cursor.fetchone()['total']
        
        print(f"Результат:")
        print(f"- Добавлено записей: {added_count}")
        print(f"- Пропущено существующих: {skipped_count}")
        print(f"- Всего обработано: {added_count + skipped_count}")
        print(f"- Всего записей для профиля в базе: {total_count}")
        
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
    add_localization_data() 