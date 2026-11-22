#!/usr/bin/env python3
"""
Скрипт для инициализации данных локализации
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.services.localization_service import LocalizationService
from app.schemas.localization import LocalizationCreate

def init_localization_data():
    """Инициализация данных локализации"""
    db = SessionLocal()
    service = LocalizationService()
    
    try:
        print("🌍 Инициализация данных локализации...")
        
        # Данные для главной страницы
        homepage_data = [
            LocalizationCreate(
                identifier="homepage_welcome_title",
                ru="ROTWK ClanWars",
                eng="ROTWK ClanWars",
                webpage="homepage"
            ),
            LocalizationCreate(
                identifier="homepage_welcome_subtitle",
                ru="Создавайте могущественные кланы, приглашайте игроков и сражайтесь за славу в эпических битвах!",
                eng="Create powerful clans, invite players and fight for glory in epic battles!",
                webpage="homepage"
            ),
            LocalizationCreate(
                identifier="homepage_login_button",
                ru="Войти",
                eng="Login",
                webpage="homepage"
            ),
            LocalizationCreate(
                identifier="homepage_register_button",
                ru="Регистрация",
                eng="Register",
                webpage="homepage"
            ),
            LocalizationCreate(
                identifier="homepage_players_stat",
                ru="Игроков",
                eng="Players",
                webpage="homepage"
            ),
            LocalizationCreate(
                identifier="homepage_clans_stat",
                ru="Кланов",
                eng="Clans",
                webpage="homepage"
            ),
            LocalizationCreate(
                identifier="homepage_create_clans_title",
                ru="Создавайте кланы",
                eng="Create Clans",
                webpage="homepage"
            ),
            LocalizationCreate(
                identifier="homepage_create_clans_desc",
                ru="Объединяйтесь с другими игроками и создавайте могущественные кланы для завоевания мира",
                eng="Unite with other players and create powerful clans to conquer the world",
                webpage="homepage"
            ),
            LocalizationCreate(
                identifier="homepage_invite_players_title",
                ru="Приглашайте игроков",
                eng="Invite Players",
                webpage="homepage"
            ),
            LocalizationCreate(
                identifier="homepage_invite_players_desc",
                ru="Расширяйте свой клан, приглашая новых участников и укрепляя свои ряды",
                eng="Expand your clan by inviting new members and strengthening your ranks",
                webpage="homepage"
            ),
            LocalizationCreate(
                identifier="homepage_fight_title",
                ru="Сражайтесь",
                eng="Fight",
                webpage="homepage"
            ),
            LocalizationCreate(
                identifier="homepage_fight_desc",
                ru="Участвуйте в эпических войнах кланов и докажите свое превосходство на поле боя",
                eng="Participate in epic clan wars and prove your superiority on the battlefield",
                webpage="homepage"
            ),
            LocalizationCreate(
                identifier="homepage_top_clans_title",
                ru="Топ кланов",
                eng="Top Clans",
                webpage="homepage"
            ),
            LocalizationCreate(
                identifier="homepage_view_button",
                ru="ПРОСМОТР",
                eng="VIEW",
                webpage="homepage"
            ),
            LocalizationCreate(
                identifier="homepage_members_count",
                ru="Участников",
                eng="Members",
                webpage="homepage"
            ),
            LocalizationCreate(
                identifier="homepage_no_clans_found",
                ru="Кланы не найдены",
                eng="No clans found",
                webpage="homepage"
            ),
        ]
        
        # Данные для навигации
        navigation_data = [
            LocalizationCreate(
                identifier="nav_home",
                ru="Главная",
                eng="Home",
                webpage="navigation"
            ),
            LocalizationCreate(
                identifier="nav_dashboard",
                ru="Кабинет",
                eng="Dashboard",
                webpage="navigation"
            ),
            LocalizationCreate(
                identifier="nav_clans",
                ru="Кланы",
                eng="Clans",
                webpage="navigation"
            ),
            LocalizationCreate(
                identifier="nav_wars",
                ru="Войны",
                eng="Wars",
                webpage="navigation"
            ),
            LocalizationCreate(
                identifier="nav_shop",
                ru="Магазин",
                eng="Shop",
                webpage="navigation"
            ),
            LocalizationCreate(
                identifier="nav_profile",
                ru="Профиль",
                eng="Profile",
                webpage="navigation"
            ),
            LocalizationCreate(
                identifier="nav_login",
                ru="Войти",
                eng="Login",
                webpage="navigation"
            ),
            LocalizationCreate(
                identifier="nav_register",
                ru="Регистрация",
                eng="Register",
                webpage="navigation"
            ),
            LocalizationCreate(
                identifier="nav_logout",
                ru="Выйти",
                eng="Logout",
                webpage="navigation"
            ),
        ]
        
        # Данные для страницы кланов
        clans_data = [
            LocalizationCreate(
                identifier="clans_page_title",
                ru="Кланы",
                eng="Clans",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_page_subtitle",
                ru="Исследуйте существующие кланы или создайте свой собственный для завоевания мира",
                eng="Explore existing clans or create your own to conquer the world",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_create_button",
                ru="Создать клан",
                eng="Create Clan",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_search_placeholder",
                ru="Поиск кланов...",
                eng="Search clans...",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_members",
                ru="Участников",
                eng="Members",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_level",
                ru="Уровень",
                eng="Level",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_experience",
                ru="Опыт",
                eng="Experience",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_join_button",
                ru="Вступить",
                eng="Join",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_view_button",
                ru="Просмотр",
                eng="View",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_delete_button",
                ru="Удалить",
                eng="Delete",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_created",
                ru="Создан",
                eng="Created",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_created_year",
                ru="Создан",
                eng="Created",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_no_description",
                ru="Описание отсутствует",
                eng="No description",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_no_clans_found",
                ru="Кланы не найдены",
                eng="No clans found",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_be_first",
                ru="Будьте первым, кто создаст клан!",
                eng="Be the first to create a clan!",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_create_dialog_title",
                ru="Создать новый клан",
                eng="Create new clan",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_name_label",
                ru="Название клана",
                eng="Clan name",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_description_label",
                ru="Описание",
                eng="Description",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_cancel_button",
                ru="Отмена",
                eng="Cancel",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_error_loading",
                ru="Ошибка при загрузке кланов",
                eng="Error loading clans",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_name_required",
                ru="Название клана обязательно",
                eng="Clan name is required",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_created_success",
                ru="Клан успешно создан!",
                eng="Clan created successfully!",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_create_error",
                ru="Ошибка при создании клана",
                eng="Error creating clan",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_application_message",
                ru="Хочу присоединиться к вашему клану!",
                eng="I want to join your clan!",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_application_sent",
                ru="Заявка отправлена!",
                eng="Application sent!",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_application_error",
                ru="Ошибка при отправке заявки",
                eng="Error sending application",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_deleted_success",
                ru="Клан удален!",
                eng="Clan deleted!",
                webpage="clans"
            ),
            LocalizationCreate(
                identifier="clans_delete_error",
                ru="Ошибка при удалении клана",
                eng="Error deleting clan",
                webpage="clans"
            ),
        ]
        
        # Объединяем все данные
        all_data = homepage_data + navigation_data + clans_data
        
        # Создаем записи
        for data in all_data:
            try:
                service.create_localization(db, data)
                print(f"✅ Создана запись: {data.identifier}")
            except Exception as e:
                print(f"⚠️  Запись {data.identifier} уже существует или ошибка: {e}")
        
        print("✅ Инициализация данных локализации завершена!")
        
    except Exception as e:
        print(f"❌ Ошибка при инициализации данных локализации: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    init_localization_data()
