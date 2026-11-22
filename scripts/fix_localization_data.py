import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models.localization import Localization
from app.repositories.localization_repository import LocalizationRepository

# Правильные русские тексты
localization_data = [
    {
        "identifier": "homepage_welcome_title",
        "ru": "ROTWK ClanWars",
        "eng": "ROTWK ClanWars",
        "webpage": "homepage"
    },
    {
        "identifier": "homepage_welcome_subtitle",
        "ru": "Создавайте могущественные кланы, приглашайте игроков и сражайтесь за славу в эпических битвах!",
        "eng": "Create powerful clans, invite players and fight for glory in epic battles!",
        "webpage": "homepage"
    },
    {
        "identifier": "homepage_login_button",
        "ru": "Войти",
        "eng": "Login",
        "webpage": "homepage"
    },
    {
        "identifier": "homepage_register_button",
        "ru": "Регистрация",
        "eng": "Register",
        "webpage": "homepage"
    },
    {
        "identifier": "homepage_players_count",
        "ru": "Игроков",
        "eng": "Players",
        "webpage": "homepage"
    },
    {
        "identifier": "homepage_clans_count",
        "ru": "Кланов",
        "eng": "Clans",
        "webpage": "homepage"
    },
    {
        "identifier": "homepage_feature_create_clans_title",
        "ru": "Создавайте кланы",
        "eng": "Create Clans",
        "webpage": "homepage"
    },
    {
        "identifier": "homepage_feature_create_clans_description",
        "ru": "Объединяйтесь с другими игроками и создавайте могущественные кланы для завоевания мира",
        "eng": "Unite with other players and create powerful clans to conquer the world",
        "webpage": "homepage"
    },
    {
        "identifier": "homepage_feature_invite_players_title",
        "ru": "Приглашайте игроков",
        "eng": "Invite Players",
        "webpage": "homepage"
    },
    {
        "identifier": "homepage_feature_invite_players_description",
        "ru": "Расширяйте свой клан, приглашая новых участников и укрепляя свои ряды",
        "eng": "Expand your clan by inviting new members and strengthening your ranks",
        "webpage": "homepage"
    },
    {
        "identifier": "homepage_feature_fight_title",
        "ru": "Сражайтесь",
        "eng": "Fight",
        "webpage": "homepage"
    },
    {
        "identifier": "homepage_feature_fight_description",
        "ru": "Участвуйте в эпических войнах кланов и докажите свое превосходство на поле боя",
        "eng": "Participate in epic clan wars and prove your superiority on the battlefield",
        "webpage": "homepage"
    },
    {
        "identifier": "homepage_top_clans_title",
        "ru": "Топ кланов",
        "eng": "Top Clans",
        "webpage": "homepage"
    },
    {
        "identifier": "homepage_clan_members_count",
        "ru": "Участников",
        "eng": "Members",
        "webpage": "homepage"
    },
    {
        "identifier": "homepage_view_clan_button",
        "ru": "ПРОСМОТР",
        "eng": "VIEW",
        "webpage": "homepage"
    },
    {
        "identifier": "homepage_no_clans_found",
        "ru": "Кланы не найдены",
        "eng": "No clans found",
        "webpage": "homepage"
    }
]

def fix_localization_data():
    db = SessionLocal()
    repo = LocalizationRepository(db)
    
    try:
        # Очищаем существующие данные
        existing_localizations = repo.get_all()
        for loc in existing_localizations:
            repo.delete(loc.identifier)
        
        print("✅ Существующие данные локализации удалены")
        
        # Создаем новые данные с правильной кодировкой
        for data in localization_data:
            repo.create(data['identifier'], data['ru'], data['eng'], data['webpage'])
            print(f"✅ Создана запись: {data['identifier']}")
        
        print("✅ Все данные локализации обновлены с правильной кодировкой")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    # Устанавливаем переменную окружения для базы данных
    os.environ['DATABASE_URL'] = "postgresql://clanwar_user:clanwar_password@localhost:5432/clanwar_db"
    fix_localization_data()
