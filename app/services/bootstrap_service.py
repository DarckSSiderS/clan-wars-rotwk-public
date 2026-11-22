from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import get_password_hash, verify_password
from app.core.admin_policy import PRIMARY_ADMIN_USERNAME, is_legacy_admin
from app.core.territory_resource_balance import TERRITORY_BALANCE
from app.core.section_55_balance import relic_cost_fields
from app.models.role import Role
from app.models.user import User
from app.models.clan import Clan, ClanMember
from app.models.achievement import Achievement
from app.models.quest import Quest, QuestType, QuestCategory
from app.models.shop import ShopItem
from app.models.territory import Territory
from app.services.territory_adjacency_service import (
    ensure_svg_territories,
    ensure_territory_adjacency,
)
from app.services.territory_ownership_service import TerritoryOwnershipService
from app.services.clan_membership_service import ClanMembershipService


DEFAULT_ROLES = {
    "admin": "Администратор системы",
    "user": "Обычный пользователь",
    "contentmaker": "Контентмейкер с доступом к социальным ссылкам",
}

STRONGHOLD_RULES = {
    name: (balance.required_territories, balance.stronghold_power)
    for name, balance in TERRITORY_BALANCE.items()
    if balance.stronghold_power > 0
}

COASTAL_TERRITORIES = {
    "Долина Митлонд", "Форлиндон", "Харлиндон", "Башенные холмы (Эмин Берайд)",
    "Форохел", "Фородвейд", "Минхириат", "Энедвайт", "Ламедон и Рингло", "Белфалас",
    "Анфалас", "Андраст", "Лебеннин", "Тол-Фалас", "Умбар", "Дальний Харад",
    "Харад (Оазис)", "Арнор", "Река Адорн",
}

PORT_TERRITORIES = {
    "Долина Митлонд", "Белфалас", "Умбар", "Энедвайт", "Тол-Фалас",
}

ADMIN_CLAN_INITIAL_RESOURCES = {
    "resources": 5000,
    "base_influence": 5000,
    "territory_points": 5000,
    "gold": 50000,
    "iron": 500,
    "wood": 500,
    "food": 500,
    "mithril": 150,
}

DEFAULT_SHOP_ITEMS = [
    {
        "name": "Пепел Мордора",
        "description": "Тёмная вулканическая тема с алыми акцентами и пепельным фоном.",
        "price": 150,
        "item_type": "site_theme",
        "rarity": "rare",
        "css_class": "theme-mordor",
        "slot": "site_theme",
        "category": "site_theme",
    },
    {
        "name": "Страж Гондора",
        "description": "Холодный камень, серебро и золото Белого Древа.",
        "price": 275,
        "item_type": "site_theme",
        "rarity": "epic",
        "css_class": "theme-gondor",
        "slot": "site_theme",
        "category": "site_theme",
    },
    {
        "name": "Лунный Имладрис",
        "description": "Ночная долина с бирюзовым светом и фиолетовой магией.",
        "price": 450,
        "item_type": "site_theme",
        "rarity": "legendary",
        "css_class": "theme-rivendell",
        "slot": "site_theme",
        "category": "site_theme",
    },
    {
        "name": "Рамка Retro Paint",
        "description": "Оригинальная рамка Paint из сохранённого Steam-профиля поверх аватара.",
        "price": 120,
        "item_type": "avatar_frame",
        "rarity": "rare",
        "css_class": "avatar-frame-palantir",
        "slot": "avatar_frame",
        "category": "avatar_frame",
    },
    {
        "name": "Летний аниме-фон",
        "description": "Оригинальный анимированный фон из сохранённого Steam-профиля.",
        "price": 180,
        "item_type": "profile_background",
        "rarity": "epic",
        "css_class": "profile-background-starlight",
        "slot": "profile_background",
        "category": "profile_background",
    },
    {
        "name": "Кольцо Пепельных гор",
        "description": "Атака +8%",
        "price": 3800,
        "item_type": "relic",
        "rarity": "legendary",
        "image_url": "/design-prototype/relic_1.webp",
        "css_class": "prototype-relic-1",
        "slot": "talisman",
        "category": "personal_relic",
    },
    {
        "name": "Брошь Серебряного листа",
        "description": "Защита +8%",
        "price": 3500,
        "item_type": "relic",
        "rarity": "legendary",
        "image_url": "/design-prototype/relic_2.webp",
        "css_class": "prototype-relic-2",
        "slot": "talisman",
        "category": "personal_relic",
    },
    {
        "name": "Посох Странника",
        "description": "Опыт +10%",
        "price": 4200,
        "item_type": "relic",
        "rarity": "legendary",
        "image_url": "/design-prototype/relic_3.webp",
        "css_class": "prototype-relic-3",
        "slot": "weapon",
        "category": "personal_relic",
    },
    {
        "name": "Клинок Первого короля",
        "description": "Критические очки +12%",
        "price": 5000,
        "item_type": "relic",
        "rarity": "legendary",
        "image_url": "/design-prototype/relic_4.webp",
        "css_class": "prototype-relic-4",
        "slot": "weapon",
        "category": "personal_relic",
    },
    {
        "name": "Камень видения",
        "description": "Разведка +1",
        "price": 2700,
        "item_type": "relic",
        "rarity": "epic",
        "image_url": "/design-prototype/relic_5.webp",
        "css_class": "prototype-relic-5",
        "slot": "special",
        "category": "personal_relic",
    },
    {
        "name": "Корона Севера",
        "description": "Влияние +6%",
        "price": 2500,
        "item_type": "relic",
        "rarity": "epic",
        "image_url": "/design-prototype/relic_6.webp",
        "css_class": "prototype-relic-6",
        "slot": "special",
        "category": "personal_relic",
    },
    {
        "name": "Знамя Белого города",
        "description": "Оборона +5%",
        "price": 1800,
        "item_type": "relic",
        "rarity": "rare",
        "image_url": "/design-prototype/relic_7.webp",
        "css_class": "prototype-relic-7",
        "slot": "banner",
        "category": "personal_relic",
    },
    {
        "name": "Рог Всадника",
        "description": "Мобильность +5%",
        "price": 1600,
        "item_type": "relic",
        "rarity": "rare",
        "image_url": "/design-prototype/relic_8.webp",
        "css_class": "prototype-relic-8",
        "slot": "special",
        "category": "personal_relic",
    },
    {
        "name": "Книга знаний",
        "description": "Опыт +5%",
        "price": 1450,
        "item_type": "relic",
        "rarity": "rare",
        "image_url": "/design-prototype/relic_9.webp",
        "css_class": "prototype-relic-9",
        "slot": "special",
        "category": "personal_relic",
    },
    {
        "name": "Колчан рейнджера",
        "description": "Атака +3%",
        "price": 900,
        "item_type": "relic",
        "rarity": "uncommon",
        "image_url": "/design-prototype/relic_10.webp",
        "css_class": "prototype-relic-10",
        "slot": "weapon",
        "category": "personal_relic",
    },
    {
        "name": "Плащ следопыта",
        "description": "Разведка +3%",
        "price": 850,
        "item_type": "relic",
        "rarity": "uncommon",
        "image_url": "/design-prototype/relic_11.webp",
        "css_class": "prototype-relic-11",
        "slot": "special",
        "category": "personal_relic",
    },
    {
        "name": "Кинжал разведчика",
        "description": "Скорость +2%",
        "price": 500,
        "item_type": "relic",
        "rarity": "common",
        "image_url": "/design-prototype/relic_12.webp",
        "css_class": "prototype-relic-12",
        "slot": "weapon",
        "category": "personal_relic",
    },
]


def ensure_shop_content(db: Session) -> None:
    """Создать или обновить стандартные товары магазина."""
    for item_data in DEFAULT_SHOP_ITEMS:
        existing = (
            db.query(ShopItem)
            .filter(
                ShopItem.item_type == item_data["item_type"],
                ShopItem.css_class == item_data["css_class"],
            )
            .first()
        )
        if existing is None:
            db.add(ShopItem(**item_data, is_active=True, is_available=True))
            continue
        for field, value in item_data.items():
            setattr(existing, field, value)
        existing.is_active = True
        existing.is_available = True
    db.commit()


def ensure_campaign_rules(db: Session) -> None:
    map_path = Path(__file__).resolve().parents[2] / "frontend" / "public" / "map-interactive.svg"
    created = set()
    if map_path.exists():
        created = set(ensure_svg_territories(db, map_path))
    for territory in db.query(Territory).all():
        territory.is_playable = True
        territory.is_coastal = territory.name in COASTAL_TERRITORIES
        territory.has_port = territory.name in PORT_TERRITORIES
        requirement, power = STRONGHOLD_RULES.get(territory.name, (0, 0))
        territory.required_territories = requirement
        territory.stronghold_power = power
        if territory.name in created:
            territory.strategic_value = territory.calculate_strategic_value()
    db.commit()
    if map_path.exists():
        ensure_territory_adjacency(db, map_path)


def _get_or_create_role(db: Session, name: str, description: str) -> Role:
    role = db.query(Role).filter(Role.name == name).first()
    if role:
        return role

    role = Role(name=name, description=description)
    db.add(role)
    db.flush()
    return role


def _unique_email(db: Session, preferred_email: str, username: str) -> str:
    if not db.query(User).filter(User.email == preferred_email).first():
        return preferred_email

    counter = 1
    while True:
        candidate = f"{username}+{counter}@example.com"
        if not db.query(User).filter(User.email == candidate).first():
            return candidate
        counter += 1


def _password_matches(password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    try:
        return verify_password(password, hashed_password)
    except Exception:
        return False


def ensure_default_admin(
    db: Session,
    *,
    create_account: bool = True,
) -> User | None:
    """Seed roles and relics, optionally creating the local test administrator."""
    roles = {
        name: _get_or_create_role(db, name, description)
        for name, description in DEFAULT_ROLES.items()
    }

    username = PRIMARY_ADMIN_USERNAME
    password = settings.DEFAULT_ADMIN_PASSWORD
    email = settings.DEFAULT_ADMIN_EMAIL
    admin_role = roles["admin"]
    user_role = roles["user"]

    user = None
    if create_account:
        for legacy_admin in db.query(User).all():
            if is_legacy_admin(legacy_admin.username):
                legacy_admin.role_id = user_role.id

        user = db.query(User).filter(User.username == username).first()
        if user:
            user.role_id = admin_role.id
            user.is_active = True
            user.is_claimed = True
            if not _password_matches(password, user.hashed_password):
                user.hashed_password = get_password_hash(password)
        else:
            user = User(
                username=username,
                email=_unique_email(db, email, username),
                hashed_password=get_password_hash(password),
                is_active=True,
                role_id=admin_role.id,
                balance=1000,
                level=10,
                experience=32000,
                language="ru",
                allow_clan_invites=True,
            )
            db.add(user)

    from app.models.clan_asset import ClanAsset
    default_assets = [
        {"key": "royal_charter", "name": "Королевская грамота", "description": "Влияние от земель: I +10%, II +20%, III +30%.", "bonus_type": "territory_points_percent", "bonus_value": 10, **relic_cost_fields("royal_charter")},
        {"key": "war_foundry", "name": "Клановая кузница", "description": "Очки за победу в войне: I +1, II +2, III +3.", "bonus_type": "war_win_points", "bonus_value": 1, **relic_cost_fields("war_foundry")},
        {"key": "mithril_standard", "name": "Мифриловый штандарт", "description": "Атака клана: I +2%, II +4%, III +6%.", "bonus_type": "attack_power", "bonus_value": 2, **relic_cost_fields("mithril_standard")},
        {"key": "granite_bastion", "name": "Гранитный бастион", "description": "Защита клана: I +2%, II +4%, III +6%.", "bonus_type": "defense_power", "bonus_value": 2, **relic_cost_fields("granite_bastion")},
        {"key": "merchant_guild", "name": "Гильдия торговцев", "description": "Цена развития населения в золоте: I -15%, II -30%, III -45%.", "bonus_type": "population_cost_percent", "bonus_value": 15, **relic_cost_fields("merchant_guild")},
        {"key": "white_tree", "name": "Знамя Белого Древа", "description": "Суточный доход золота: I +8%, II +16%, III +24%.", "bonus_type": "gold_income_percent", "bonus_value": 8, **relic_cost_fields("white_tree")},
        {"key": "red_arrow", "name": "Красная стрела Рохана", "description": "Атака клана: I +1%, II +2%, III +3%.", "bonus_type": "attack_power", "bonus_value": 1, **relic_cost_fields("red_arrow")},
        {"key": "iron_crown", "name": "Железная корона", "description": "Защита клана: I +1%, II +2%, III +3%.", "bonus_type": "defense_power", "bonus_value": 1, **relic_cost_fields("iron_crown")},
        {"key": "palantir", "name": "Палантир Ортханка", "description": "Влияние от земель: I +2%, II +4%, III +6%.", "bonus_type": "territory_points_percent", "bonus_value": 2, **relic_cost_fields("palantir")},
        {"key": "dwarf_anvil", "name": "Наковальня Глубин", "description": "Цена укреплений в золоте: I -12%, II -24%, III -36%.", "bonus_type": "fortification_cost_percent", "bonus_value": 12, **relic_cost_fields("dwarf_anvil")},
        {"key": "ents_seed", "name": "Семя Энтов", "description": "Прирост населения за уровень: базовые +4% и +20 жителей; реликвия добавляет I +1%, II +2%, III +3%.", "bonus_type": "population_growth_percent", "bonus_value": 10, **relic_cost_fields("ents_seed")},
        {"key": "mordor_forge", "name": "Кузни Барад-дура", "description": "Атака клана: I +2%, II +4%, III +6%.", "bonus_type": "attack_power", "bonus_value": 2, **relic_cost_fields("mordor_forge")},
        {"key": "helms_horn", "name": "Рог Хельмовой Пади", "description": "Защита клана: I +2%, II +4%, III +6%.", "bonus_type": "defense_power", "bonus_value": 2, **relic_cost_fields("helms_horn")},
        {"key": "ring_of_barahir", "name": "Кольцо Барахира", "description": "Влияние от земель: I +5%, II +10%, III +15%.", "bonus_type": "territory_points_percent", "bonus_value": 5, **relic_cost_fields("ring_of_barahir")},
        {"key": "galadhrim_mirror", "name": "Зеркало Галадриэли", "description": "Каждая земля добывает дополнительно: I +1, II +2, III +3 ресурса в сутки.", "bonus_type": "resource_income_flat", "bonus_value": 1, **relic_cost_fields("galadhrim_mirror")},
    ]
    for asset_data in default_assets:
        existing_asset = db.query(ClanAsset).filter(ClanAsset.key == asset_data["key"]).first()
        asset_data.update({
            "required_influence_level_1": 175,
            "required_influence_level_2": 525,
            "required_influence_level_3": 1050,
        })
        if not existing_asset:
            db.add(ClanAsset(**asset_data))

    db.commit()
    if user is not None:
        db.refresh(user)
    return user


def ensure_admin_test_clan(db: Session) -> Clan:
    """Create the protected Tol-Falas sandbox without touching normal clans."""
    admin_role = _get_or_create_role(db, "admin", DEFAULT_ROLES["admin"])
    admin_user = (
        db.query(User)
        .filter(User.username == settings.ADMIN_CLAN_USERNAME)
        .first()
    )
    if admin_user:
        admin_user.role_id = admin_role.id
        admin_user.is_active = True
        admin_user.is_claimed = True
        if not _password_matches(
            settings.ADMIN_CLAN_PASSWORD,
            admin_user.hashed_password,
        ):
            admin_user.hashed_password = get_password_hash(
                settings.ADMIN_CLAN_PASSWORD
            )
    else:
        admin_user = User(
            username=settings.ADMIN_CLAN_USERNAME,
            email=_unique_email(
                db,
                settings.ADMIN_CLAN_EMAIL,
                settings.ADMIN_CLAN_USERNAME,
            ),
            hashed_password=get_password_hash(settings.ADMIN_CLAN_PASSWORD),
            is_active=True,
            is_claimed=True,
            role_id=admin_role.id,
            balance=1000,
            level=10,
            experience=32000,
            language="ru",
            allow_clan_invites=True,
        )
        db.add(admin_user)
        db.flush()

    clan = (
        db.query(Clan)
        .filter(Clan.is_admin_clan.is_(True))
        .order_by(Clan.id)
        .first()
    )
    existing_membership = (
        db.query(ClanMember)
        .filter(ClanMember.user_id == admin_user.id)
        .first()
    )
    if clan is None:
        clan = (
            db.query(Clan)
            .filter(Clan.name == settings.ADMIN_CLAN_NAME)
            .first()
        )
    if clan is None:
        if existing_membership:
            raise ValueError(
                f"Admin test user {admin_user.username} already belongs to clan "
                f"{existing_membership.clan_id}"
            )
        clan = Clan(
            name=settings.ADMIN_CLAN_NAME,
            description=(
                "Системный клан для проверки войн, экономики, земель, "
                "реликвий и торговли. Вступление только по назначению администратора."
            ),
            leader_id=admin_user.id,
            level=10,
            experience=50000,
            max_members=20,
            is_admin_clan=True,
            **ADMIN_CLAN_INITIAL_RESOURCES,
        )
        db.add(clan)
        db.flush()
    else:
        clan.is_admin_clan = True
        clan.leader_id = admin_user.id

    # Административный клан не участвует в цветовой разметке кампании.
    clan.map_color = None
    clan.map_color_change_used = False

    if existing_membership and existing_membership.clan_id != clan.id:
        raise ValueError(
            f"Admin test user {admin_user.username} already belongs to clan "
            f"{existing_membership.clan_id}"
        )
    if not existing_membership:
        existing_membership = ClanMember(
            user_id=admin_user.id,
            clan_id=clan.id,
            rank="Глава клана",
            is_trader=True,
        )
        db.add(existing_membership)
        db.flush()
    ClanMembershipService().start(
        db,
        existing_membership,
        reason="admin_sandbox_bootstrap",
    )

    tol_falas = (
        db.query(Territory)
        .filter(Territory.name == "Тол-Фалас")
        .first()
    )
    if not tol_falas:
        raise ValueError("Тол-Фалас отсутствует в базе территорий")
    TerritoryOwnershipService().transfer(
        db,
        tol_falas,
        clan.id,
        reason="admin_sandbox",
    )
    tol_falas.status = "active"
    tol_falas.is_playable = True
    tol_falas.is_coastal = True
    tol_falas.has_port = True
    tol_falas.resource_wealth = max(tol_falas.resource_wealth or 0, 180)
    tol_falas.population = max(tol_falas.population or 0, 25000)
    tol_falas.resource_type = "mithril"
    tol_falas.resource_output = max(tol_falas.resource_output or 0, 2)

    db.commit()
    db.refresh(clan)
    return clan


def ensure_progression_content(db: Session) -> None:
    """Создать и обновить стандартные достижения и задания профиля."""
    def achievement(name, description, requirement_type, target, category="combat", rarity="common", points=10, reward=50, icon="axeswb.png"):
        return {
            "name": name, "description": description, "icon": icon,
            "category": category, "rarity": rarity, "points": points,
            "requirement_type": requirement_type, "requirement_value": target,
            "target_value": target, "reward_amount": reward,
        }

    tier_definitions = [
        ("bronze", "Бронза", "common", 40, 150),
        ("silver", "Серебро", "rare", 120, 500),
        ("gold", "Золото", "epic", 350, 1500),
        ("crystal", "Кристалл", "legendary", 1000, 5000),
    ]

    def tier_series(key, title, requirement, targets, category="combat", icon="axeswb.png"):
        items = []
        for target, (tier, tier_label, rarity, points, reward) in zip(targets, tier_definitions):
            item = achievement(
                f"{key}_{tier}",
                f"{title}. {tier_label}: {target}",
                requirement,
                target,
                category,
                rarity,
                points,
                reward,
                icon,
            )
            item["achievement_type"] = key
            items.append(item)
        return items

    achievements = [
        achievement("first_battle", "Сыграйте первый матч", "matches", 1),
        achievement("first_win", "Одержите первую победу", "wins", 1, points=15, reward=75),
    ]
    achievements.extend(tier_series("career_matches", "Сыграйте рейтинговые матчи", "matches", [10, 50, 200, 1000], icon="towerwb.png"))
    achievements.extend(tier_series("career_wins", "Одержите победы", "wins", [10, 50, 200, 1000], icon="sauronwb.png"))
    achievements.extend(tier_series("winning_streak", "Соберите победную серию", "best_streak", [3, 10, 50, 200], icon="sauronwb.png"))
    achievements.extend(tier_series("battle_hardened", "Продолжайте играть после поражений", "losses", [10, 50, 200, 1000]))
    achievements.extend(tier_series("map_explorer", "Откройте разные карты", "unique_maps", [5, 15, 30, 60], "exploration", "towerwb.png"))
    achievements.extend(tier_series("faction_explorer", "Сыграйте за разные фракции", "unique_factions", [3, 7, 10, 15], "exploration"))
    achievements.extend(tier_series("long_battles", "Проведите матчи дольше 30 минут", "long_games", [5, 25, 100, 500], "mastery", "towerwb.png"))
    achievements.extend(tier_series("fast_victories", "Победите быстрее 10 минут", "fast_wins", [5, 25, 100, 500], "mastery", "sauronwb.png"))
    achievements.extend(tier_series("night_battles", "Сыграйте матчи ночью", "night_matches", [10, 50, 200, 1000], "mastery", "sauronwb.png"))
    achievements.extend(tier_series("different_opponents", "Победите разных соперников", "unique_opponents", [5, 25, 100, 500], "social"))
    achievements.extend(tier_series("active_days", "Играйте в разные дни", "active_days", [7, 30, 120, 365], "social"))

    superseded_achievement_names = {
        "veteran", "seasoned", "centurion", "legend", "marathon", "immortal",
        "warrior", "conqueror", "warlord", "champion", "victor",
        "unstoppable", "dominant", "perfect_war", "survivor",
        "map_roamer", "cartographer", "map_master",
        "faction_apprentice", "faction_scholar", "faction_master",
        "gondor_banner", "rohan_banner", "isengard_banner", "mordor_banner",
        "angmar_banner", "lothlorien_banner", "long_battle", "epic_battler",
        "speed_runner", "night_warrior", "rival", "nemesis", "dedicated",
        "seasoned_commander",
    }
    tracked_factions = [
        "Гондор", "Рохан", "Изенгард", "Мордор", "Ангмар", "Гномы",
        "Эльфы", "Гоблины", "Люди", "Лотлориэн",
    ]
    tracked_maps = [
        "Fords of Isen", "Brandy Hills", "Rhudaur", "Plains of Lindon",
        "Chetwood", "Greenham", "Ephel Duath", "Jungles of Far Harad",
        "Frozen Shallows of Isen", "Lossarnach II", "Troll-fells",
    ]
    for faction in tracked_factions:
        slug = faction.lower().replace(" ", "_")
        games_key = f"faction_games:{faction}"
        wins_key = f"faction_wins:{faction}"
        winrate_key = f"faction_winrate:{faction}"
        achievements.extend(tier_series(games_key, f"Сыграйте матчи за фракцию «{faction}»", games_key, [10, 50, 200, 1000], "factions"))
        achievements.extend(tier_series(wins_key, f"Побеждайте за фракцию «{faction}»", wins_key, [10, 50, 200, 1000], "factions", "sauronwb.png"))
        for minimum_games, (tier, tier_label, rarity, points, reward) in zip([10, 50, 200, 1000], tier_definitions):
            item = achievement(
                f"{slug}_winrate_{tier}",
                f"Удерживайте винрейт не ниже 60% за фракцию «{faction}» после {minimum_games} матчей. Ступень: {tier_label}",
                f"faction_winrate:{faction}:60:{minimum_games}",
                60,
                "factions",
                rarity,
                points,
                reward,
                "sauronwb.png",
            )
            item["achievement_type"] = winrate_key
            achievements.append(item)
        superseded_achievement_names.update({
            f"{slug}_games_10", f"{slug}_games_50", f"{slug}_winrate",
        })
    for map_name in tracked_maps:
        slug = map_name.lower().replace(" ", "_").replace("-", "_")
        games_key = f"map_games:{map_name}"
        wins_key = f"map_wins:{map_name}"
        winrate_key = f"map_winrate:{map_name}"
        achievements.extend(tier_series(games_key, f"Сыграйте матчи на карте «{map_name}»", games_key, [5, 25, 100, 500], "maps", "towerwb.png"))
        achievements.extend(tier_series(wins_key, f"Побеждайте на карте «{map_name}»", wins_key, [5, 25, 100, 500], "maps", "sauronwb.png"))
        for minimum_games, (tier, tier_label, rarity, points, reward) in zip([10, 50, 200, 1000], tier_definitions):
            item = achievement(
                f"map_{slug}_winrate_{tier}",
                f"Удерживайте винрейт не ниже 60% на карте «{map_name}» после {minimum_games} матчей. Ступень: {tier_label}",
                f"map_winrate:{map_name}:60:{minimum_games}",
                60,
                "maps",
                rarity,
                points,
                reward,
                "sauronwb.png",
            )
            item["achievement_type"] = winrate_key
            achievements.append(item)
        superseded_achievement_names.update({
            f"map_{slug}_games_5", f"map_{slug}_games_25", f"map_{slug}_winrate",
        })

    team_modes = [
        ("1 versus 1", "1v1"),
        ("2 versus 2", "2v2"),
        ("3 versus 3", "3v3"),
        ("4 versus 4", "4v4"),
    ]
    team_tiers = [
        (10, "bronze", "бронза", "common", 40, 150),
        (50, "silver", "серебро", "rare", 120, 500),
        (200, "gold", "золото", "epic", 350, 1500),
        (1000, "crystal", "кристалл", "legendary", 1000, 5000),
    ]
    for mode, short_mode in team_modes:
        for target, tier, tier_label, rarity, points, reward in team_tiers:
            game_item = achievement(
                f"mode_{short_mode}_games_{tier}",
                f"Сыграйте {target} рейтинговых матчей {short_mode} — ступень: {tier_label}",
                f"mode_games:{mode}",
                target,
                "teamplay",
                rarity,
                points,
                reward,
                "axeswb.png",
            )
            game_item["achievement_type"] = f"mode_{short_mode}_games"
            win_item = achievement(
                f"mode_{short_mode}_wins_{tier}",
                f"Победите в {target} рейтинговых матчах {short_mode} — ступень: {tier_label}",
                f"mode_wins:{mode}",
                target,
                "teamplay",
                rarity,
                points,
                reward,
                "sauronwb.png",
            )
            win_item["achievement_type"] = f"mode_{short_mode}_wins"
            achievements.extend([game_item, win_item])

    for target, tier, tier_label, rarity, points, reward in team_tiers:
        team_item = achievement(
            f"team_games_{tier}",
            f"Сыграйте {target} командных матчей 2v2–4v4 — ступень: {tier_label}",
            "team_games",
            target,
            "teamplay",
            rarity,
            points,
            reward,
            "towerwb.png",
        )
        team_item["achievement_type"] = "team_games"
        team_win_item = achievement(
            f"team_wins_{tier}",
            f"Победите в {target} командных матчах 2v2–4v4 — ступень: {tier_label}",
            "team_wins",
            target,
            "teamplay",
            rarity,
            points,
            reward,
            "sauronwb.png",
        )
        team_win_item["achievement_type"] = "team_wins"
        achievements.extend([team_item, team_win_item])

    canonical_names = set()
    for data in achievements:
        canonical_names.add(data["name"])
        existing = db.query(Achievement).filter(Achievement.name == data["name"]).first()
        if not existing:
            db.add(Achievement(**data, is_active=True, is_available=True))
            continue
        for field, value in data.items():
            setattr(existing, field, value)
        existing.is_active = True
        existing.is_available = True

    # Старые отдельные карточки сохраняются в базе ради истории наград,
    # но больше не показываются и не участвуют в новом прогрессе.
    if superseded_achievement_names:
        db.query(Achievement).filter(
            Achievement.name.in_(superseded_achievement_names - canonical_names)
        ).update(
            {Achievement.is_active: False, Achievement.is_available: False},
            synchronize_session=False,
        )

    quests = [
        ("quest_daily_first_win", "quest_daily_first_win_desc", QuestType.DAILY, QuestCategory.WINS, 1, 100, 50),
        ("quest_daily_winner", "quest_daily_winner_desc", QuestType.DAILY, QuestCategory.WINS, 5, 500, 200),
        ("quest_daily_active_player", "quest_daily_active_player_desc", QuestType.DAILY, QuestCategory.MATCHES_PLAYED, 3, 150, 75),
        ("quest_daily_win_streak", "quest_daily_win_streak_desc", QuestType.DAILY, QuestCategory.STREAK, 3, 300, 150),
        ("Сыграйте два матча", "Завершите 2 матча за день", QuestType.DAILY, QuestCategory.MATCHES_PLAYED, 2, 80, 40),
        ("Победная охота", "Одержите 3 победы за день", QuestType.DAILY, QuestCategory.WINS, 3, 260, 120),
        ("Разминка армии", "Сыграйте 5 матчей за день", QuestType.DAILY, QuestCategory.MATCHES_PLAYED, 5, 350, 180),
        ("Тройной удар", "Выиграйте 3 матча подряд", QuestType.DAILY, QuestCategory.STREAK, 3, 320, 160),
        ("Десять минут славы", "Одержите 7 побед за день", QuestType.DAILY, QuestCategory.WINS, 7, 700, 300),
        ("Поле боя зовет", "Сыграйте 8 матчей за день", QuestType.DAILY, QuestCategory.MATCHES_PLAYED, 8, 650, 300),
        ("quest_weekly_winner", "quest_weekly_winner_desc", QuestType.WEEKLY, QuestCategory.WINS, 10, 1000, 500),
        ("quest_weekly_player", "quest_weekly_player_desc", QuestType.WEEKLY, QuestCategory.MATCHES_PLAYED, 25, 800, 400),
        ("Недельный натиск", "Одержите 20 побед за неделю", QuestType.WEEKLY, QuestCategory.WINS, 20, 1800, 900),
        ("Командир недели", "Сыграйте 40 матчей за неделю", QuestType.WEEKLY, QuestCategory.MATCHES_PLAYED, 40, 1600, 800),
        ("Без пощады", "Выиграйте 5 матчей подряд за неделю", QuestType.WEEKLY, QuestCategory.STREAK, 5, 1300, 650),
        ("Большая серия", "Одержите 30 побед за неделю", QuestType.WEEKLY, QuestCategory.WINS, 30, 2600, 1300),
        ("Арена не спит", "Сыграйте 60 матчей за неделю", QuestType.WEEKLY, QuestCategory.MATCHES_PLAYED, 60, 2400, 1200),
        ("Железная воля", "Выиграйте 10 матчей подряд за неделю", QuestType.WEEKLY, QuestCategory.STREAK, 10, 3000, 1500),
        ("Путь ветерана", "Сыграйте 75 матчей за неделю", QuestType.WEEKLY, QuestCategory.MATCHES_PLAYED, 75, 3200, 1600),
        ("Неделя победителя", "Одержите 40 побед за неделю", QuestType.WEEKLY, QuestCategory.WINS, 40, 4000, 2000),
    ]
    for title_key, description_key, quest_type, category, target, coins, xp in quests:
        existing = db.query(Quest).filter(Quest.title_key == title_key).first()
        if not existing:
            db.add(Quest(
                title_key=title_key, description_key=description_key,
                quest_type=quest_type, category=category, target_value=target,
                reward_coins=coins, reward_experience=xp, is_active=True,
            ))
    db.commit()
