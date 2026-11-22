"""Явные доходы карты по рабочей таблице от 18.10.2026.

Нет подключения к БД, миграций, запуска сезона или записи при импорте.
Доверенный вызывающий код передаёт сессию изолированной репетиции и время.
По умолчанию выполняется только проверка; apply=True создаёт недостающие
профили во вложенной транзакции, без commit и без изменения самой карты.
"""

from dataclasses import dataclass, replace
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import as_utc
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.cycle_economy import CycleEconomyState
from app.models.cycle_income import CycleIncomeAccrual, CycleTerritoryProfile
from app.models.territory import Territory
from app.services.campaign_cycle_service import _utc
from app.services.cycle_economy import Resources
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_income_service import CycleIncomeService


INCOME_CATALOG_VERSION = 'territory_income_2026_10_18_v1'


@dataclass(frozen=True)
class IncomeCatalogEntry:
    """source_id обозначает строку исходной таблицы, а не идентичность карты."""

    source_id: int
    name: str
    base: Resources
    profile_material: str | None
    influence_value: int
    is_playable: bool = True
    has_port: bool = False
    fortress: bool = False


# Доходы назначены явно: ни флаги карты, ни старый баланс их не вычисляют.
INCOME_CATALOG = (
    IncomeCatalogEntry(1, 'Эвендим', Resources(100, food=4), 'food', 50),
    IncomeCatalogEntry(2, 'Рун', Resources(150, food=6), 'food', 50),
    IncomeCatalogEntry(3, 'Арнор', Resources(100, food=4), 'food', 50),
    IncomeCatalogEntry(4, 'Форност', Resources(150, iron=6), 'iron', 50),
    IncomeCatalogEntry(5, 'Троллистое плато', Resources(100, wood=4), 'wood', 50),
    IncomeCatalogEntry(6, 'Долина Митлонд', Resources(150, wood=4), 'wood', 50, has_port=True),
    IncomeCatalogEntry(7, 'Форлиндон', Resources(150, wood=6), 'wood', 50),
    IncomeCatalogEntry(8, 'Харлиндон', Resources(150, wood=6), 'wood', 50),
    IncomeCatalogEntry(9, 'Шир', Resources(200, food=8), 'food', 50),
    IncomeCatalogEntry(10, 'Башенные холмы (Эмин Берайд)', Resources(100, iron=4), 'iron', 50),
    IncomeCatalogEntry(11, 'Ривенделл (Имладрис)', Resources(300, wood=8), 'wood', 90, fortress=True),
    IncomeCatalogEntry(12, 'Эрегион (Холлин)', Resources(150, iron=6), 'iron', 50),
    IncomeCatalogEntry(13, 'Высокий Перевал', Resources(100, iron=4), 'iron', 50),
    IncomeCatalogEntry(14, 'Врата Мории', Resources(150, mithril=1), 'mithril', 50),
    IncomeCatalogEntry(15, 'Перевал Карадрас', Resources(100, mithril=1), 'mithril', 50),
    IncomeCatalogEntry(16, 'Долина Азанулбизар (Димрил-Дейл)', Resources(100, iron=4), 'iron', 50),
    IncomeCatalogEntry(17, 'Чернолесье (Темнолесье)', Resources(200, wood=8), 'wood', 50),
    IncomeCatalogEntry(18, 'Дол Гулдур', Resources(300, wood=8), 'wood', 90, fortress=True),
    IncomeCatalogEntry(19, 'Дейл', Resources(200, food=8), 'food', 50),
    IncomeCatalogEntry(20, 'Подземелья Эребора', Resources(350, iron=8), 'iron', 120, fortress=True),
    IncomeCatalogEntry(21, 'Железные холмы', Resources(200, iron=8), 'iron', 50),
    IncomeCatalogEntry(22, 'Степи Рованиона', Resources(150, food=6), 'food', 50),
    IncomeCatalogEntry(23, 'Келдуин', Resources(150, food=6), 'food', 50),
    IncomeCatalogEntry(24, 'Эред Митрин (Серые горы)', Resources(100, iron=4), 'iron', 50),
    IncomeCatalogEntry(25, 'Гора Гундабад', Resources(150, iron=6), 'iron', 50),
    IncomeCatalogEntry(26, 'Каррок', Resources(100, food=4), 'food', 50),
    IncomeCatalogEntry(27, 'Восточный Эмнет', Resources(150, food=6), 'food', 50),
    IncomeCatalogEntry(28, 'Волд', Resources(100, food=4), 'food', 50),
    IncomeCatalogEntry(29, 'Хельмова Падь (Западная Марка)', Resources(350, iron=8), 'iron', 120, fortress=True),
    IncomeCatalogEntry(30, 'Фангорн', Resources(200, wood=8), 'wood', 50),
    IncomeCatalogEntry(31, 'Дунланд', Resources(100, food=4), 'food', 50),
    IncomeCatalogEntry(32, 'Изенские броды', Resources(100, food=4), 'food', 50),
    IncomeCatalogEntry(33, 'Река Адорн', Resources(100, food=4), 'food', 50),
    IncomeCatalogEntry(34, 'Изенгард', Resources(300, iron=8), 'iron', 90, fortress=True),
    IncomeCatalogEntry(35, 'Осгилиат', Resources(150, iron=6), 'iron', 50),
    IncomeCatalogEntry(36, 'Минас Тирит', Resources(400, iron=8), 'iron', 160, fortress=True),
    IncomeCatalogEntry(37, 'Пеленнорские поля', Resources(200, food=8), 'food', 50),
    IncomeCatalogEntry(38, 'Центральный Итилиен', Resources(150, food=6), 'food', 50),
    IncomeCatalogEntry(39, 'Итилиенские холмы', Resources(150, wood=6), 'wood', 50),
    IncomeCatalogEntry(40, 'Ламедон и Рингло', Resources(150, food=6), 'food', 50),
    IncomeCatalogEntry(41, 'Белфалас', Resources(150, food=4), 'food', 50, has_port=True),
    IncomeCatalogEntry(42, 'Анфалас', Resources(100, food=4), 'food', 50),
    IncomeCatalogEntry(43, 'Андраст', Resources(100, wood=4), 'wood', 50),
    IncomeCatalogEntry(44, 'Умбар', Resources(300, wood=8), 'wood', 90, has_port=True, fortress=True),
    IncomeCatalogEntry(45, 'Чёрные Врата (Мораннон)', Resources(150, iron=6), 'iron', 50),
    IncomeCatalogEntry(46, 'Дагорлад', Resources(100, iron=4), 'iron', 50),
    IncomeCatalogEntry(47, 'Мёртвые Топи', Resources(100, iron=4), 'iron', 50),
    IncomeCatalogEntry(48, 'Удун', Resources(400, iron=8), 'iron', 160, fortress=True),
    IncomeCatalogEntry(49, 'Роковая Гора (Ородруин)', Resources(200, iron=8), 'iron', 50),
    IncomeCatalogEntry(50, 'Минас Моргул', Resources(350, iron=8), 'iron', 120, fortress=True),
    IncomeCatalogEntry(51, 'Мордорские пустоши', Resources(100, iron=4), 'iron', 50),
    IncomeCatalogEntry(52, 'Море Нурнен', Resources(200, food=8), 'food', 50),
    IncomeCatalogEntry(53, 'Северный Рун', Resources(150, food=6), 'food', 50),
    IncomeCatalogEntry(54, 'Дальний Харад', Resources(100, food=4), 'food', 50),
    IncomeCatalogEntry(55, 'Харад (Оазис)', Resources(200, food=8), 'food', 50),
    IncomeCatalogEntry(56, 'Энедвайт', Resources(150, wood=4), 'wood', 50, has_port=True),
    IncomeCatalogEntry(57, 'Ближние земли Кханда', Resources(100, iron=4), 'iron', 50),
    IncomeCatalogEntry(58, 'Бурые равнины', Resources(100, food=4), 'food', 50),
    IncomeCatalogEntry(59, 'Заверть', Resources(100, iron=4), 'iron', 50),
    IncomeCatalogEntry(60, 'Западная марка (Шир)', Resources(200, food=8), 'food', 50),
    IncomeCatalogEntry(61, 'Кардолан', Resources(100, food=4), 'food', 50),
    IncomeCatalogEntry(62, 'Карн Дум', Resources(350, iron=8), 'iron', 120, fortress=True),
    IncomeCatalogEntry(63, 'Курганы (Тирн-Гортхад)', Resources(100, iron=4), 'iron', 50),
    IncomeCatalogEntry(64, 'Лес Друадан', Resources(150, wood=6), 'wood', 50),
    IncomeCatalogEntry(65, 'Лес Зелёной Листвы', Resources(200, wood=8), 'wood', 50),
    IncomeCatalogEntry(66, 'Лострианд', Resources(150, wood=6), 'wood', 50),
    IncomeCatalogEntry(67, 'Минхириат', Resources(100, wood=4), 'wood', 50),
    IncomeCatalogEntry(68, 'Рудаур', Resources(100, iron=4), 'iron', 50),
    IncomeCatalogEntry(69, 'Форохел', Resources(100, food=4), 'food', 50),
    IncomeCatalogEntry(70, 'Фородвейд', Resources(100, food=4), 'food', 50),
    IncomeCatalogEntry(71, 'Северные холмы', Resources(100, food=4), 'food', 50),
    IncomeCatalogEntry(72, 'Бри', Resources(150, food=6), 'food', 50),
    IncomeCatalogEntry(73, 'Лебеннин', Resources(200, food=8), 'food', 50),
    IncomeCatalogEntry(74, 'Восточный Рохан', Resources(150, food=6), 'food', 50),
    IncomeCatalogEntry(75, 'Эмин Муил', Resources(100, iron=4), 'iron', 50),
    IncomeCatalogEntry(76, 'Тол-Фалас', Resources(), None, 0, is_playable=False),
)


@dataclass(frozen=True)
class IncomeCatalogPreparation:
    """Проверенное сопоставление; суммы и влияние не являются выдачей клану."""

    catalog_version: str
    profiles: tuple[tuple[int, IncomeCatalogEntry], ...]
    missing_territory_ids: tuple[int, ...]
    created_territory_ids: tuple[int, ...] = ()


def _read(db, statement, *, lock):
    if lock:
        statement = statement.with_for_update()
    return db.execute(statement.execution_options(populate_existing=True))


def _prepare(db, *, season_id, now, lock):
    # Порядок совпадает с сервисом доходов: циклы -> сезон -> земли -> профили.
    cycles = list(_read(db, select(CampaignCycleRecord).where(
        CampaignCycleRecord.season_id == season_id).order_by(CampaignCycleRecord.number.desc()),
        lock=lock).scalars())
    season = _read(db, select(CampaignSeason).where(CampaignSeason.id == season_id),
                   lock=lock).scalar_one_or_none()
    if season is None or (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
        raise ValueError('Требуется существующий сезон с механикой cycle_v1')

    lands = list(_read(db, select(Territory).order_by(Territory.id), lock=lock).scalars())
    by_name = {entry.name: entry for entry in INCOME_CATALOG}
    seen, assignments = set(), []
    for land in lands:
        if land.name in seen:
            raise ValueError(f'Повтор имени земли: {land.name!r}; сопоставление неоднозначно')
        seen.add(land.name)
        entry = by_name.get(land.name)
        if entry is None:
            raise ValueError(f'Неизвестная земля: {land.name!r}, ID {land.id}')
        checks = (
            ('игровой статус', land.is_playable, entry.is_playable),
            ('порт', land.has_port, entry.has_port),
            ('крепость', land.is_great_stronghold, entry.fortress),
            ('влияние', land.influence_value, entry.influence_value),
        )
        for label, actual, expected in checks:
            if actual != expected:
                raise ValueError(f'Земля {land.name!r}, ID {land.id}: {label} '
                                 f'не совпадает с каталогом ({actual!r} вместо {expected!r})')
        if entry.is_playable:
            if land.resource_type != entry.profile_material:
                raise ValueError(f'Земля {land.name!r}, ID {land.id}: материал не совпадает с каталогом')
            if not isinstance(land.resource_output, int) or land.resource_output <= 0:
                raise ValueError(f'Земля {land.name!r}, ID {land.id}: профильная добыча должна быть положительной')
            assignments.append((land.id, entry))
    missing_names = by_name.keys() - seen
    if missing_names:
        raise ValueError('Отсутствуют земли каталога: ' + ', '.join(sorted(missing_names)))

    expected = dict(assignments)
    existing = list(_read(db, select(CycleTerritoryProfile).where(
        CycleTerritoryProfile.season_id == season_id).order_by(CycleTerritoryProfile.territory_id),
        lock=lock).scalars())
    for row in existing:
        entry = expected.get(row.territory_id)
        if entry is None:
            raise ValueError(f'Лишний сезонный профиль: ID {row.territory_id}; '
                             'земля отсутствует или неигровая')
        try:
            if not isinstance(row.base, dict):
                raise TypeError
            base = Resources(**row.base)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'Некорректный сезонный профиль: {entry.name!r}, ID {row.territory_id}') from exc
        if base != entry.base or row.profile_material != entry.profile_material:
            raise ValueError(f'Конфликтующий сезонный профиль: {entry.name!r}, ID {row.territory_id}')

    configured = {row.territory_id for row in existing}
    missing_ids = tuple(territory_id for territory_id, _ in assignments if territory_id not in configured)
    if lock and missing_ids:
        if any(as_utc(cycle.preparation_at) <= now for cycle in cycles):
            raise ValueError('Нельзя создавать профили после начала подготовки')
        if db.execute(select(CycleIncomeAccrual.state_id).join(CycleEconomyState).where(
                CycleEconomyState.season_id == season_id)).first():
            raise ValueError('Нельзя создавать профили после первого начисления дохода')
    return IncomeCatalogPreparation(INCOME_CATALOG_VERSION, tuple(assignments), missing_ids)


def prepare_income_profiles(db: Session, *, season_id: int, catalog_version: str,
                            now: datetime, apply: bool = False) -> IncomeCatalogPreparation:
    """Проверить всю карту и сезонные профили; явно создать только недостающие.

    Разрешён только доверенный вызов для изолированного старта/репетиции.
    Вызывающий код явно выполняет flush до вызова и владеет внешней транзакцией.
    При apply=True все проверки и вставки защищены общей вложенной транзакцией.
    Конфликты не исправляются; повторный вызов не меняет совпавшие профили.
    Результат без missing_territory_ids означает полноту именно этого каталога.
    Версию надо сохранять в манифесте репетиции; модель профиля её не хранит.
    """
    if catalog_version != INCOME_CATALOG_VERSION:
        raise ValueError(f'Неизвестная версия каталога: {catalog_version!r}')
    if type(apply) is not bool:
        raise TypeError('Параметр apply должен быть логическим значением')
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Требуется дата со сведениями о часовом поясе')
    now = _utc(now)
    if db.new or db.dirty or db.deleted:
        raise ValueError('Сначала явно выполните flush изменений вызывающего кода')

    with db.no_autoflush:
        if not apply:
            return _prepare(db, season_id=season_id, now=now, lock=False)
        with CycleEconomyStore._atomic(db):
            result = _prepare(db, season_id=season_id, now=now, lock=True)
            missing = set(result.missing_territory_ids)
            service = CycleIncomeService()
            for territory_id, entry in result.profiles:
                if territory_id in missing:
                    service.configure_profile(db, season_id=season_id, territory_id=territory_id,
                        base=entry.base, profile_material=entry.profile_material, now=now)
            return replace(result, missing_territory_ids=(),
                           created_territory_ids=result.missing_territory_ids)
