"""Проверки явного каталога и подготовки только на БД в памяти."""

from datetime import datetime, timedelta, timezone
from importlib import import_module, util
from pathlib import Path

import pytest
from sqlalchemy import event, select, update

from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.clan import Clan
from app.models.cycle_economy import CycleEconomyState
from app.models.cycle_income import CycleIncomeAccrual, CycleTerritoryProfile
from app.models.territory import Territory, TerritoryOwnershipHistory
from app.services.cycle_economy import Resources
from app.services.cycle_income_service import CycleIncomeService


NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)
VERSION = 'territory_income_2026_10_18_v1'
MODULE = 'app.services.cycle_income_catalog'


def _catalog():
    assert util.find_spec(MODULE) is not None, 'Модуль явного каталога ещё не реализован'
    return import_module(MODULE)


def _proposal():
    """Ожидания берутся из исходной таблицы, независимо от реализации каталога."""
    path = Path(__file__).resolve().parents[1] / 'docs/TERRITORY_INCOME_PROPOSAL_2026-10-18.md'
    materials = {'железа': 'iron', 'дерева': 'wood', 'еды': 'food', 'мифрил': 'mithril'}
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if len(cells) != 7 or not cells[0].isdigit():
            continue
        source_id, name, category, gold, production, influence, _ = cells
        material, amount = None, 0
        if production != 'Нет':
            quantity, label = production.split()
            material, amount = materials[label], int(quantity)
        rows.append(dict(source_id=int(source_id), name=name,
            is_playable=int(source_id) != 76,
            has_port=category in ('Порт', 'Крепость и порт'),
            fortress=category in ('Крепость', 'Крепость и порт'),
            profile_material=material, influence_value=int(influence),
            base=Resources(gold=int(gold), **({material: amount} if material else {}))))
    assert len(rows) == 76
    return rows


@pytest.fixture
def world(db):
    assert db.get_bind().url.database in (None, '', ':memory:')
    season = CampaignSeason(number=1, name='Репетиция каталога', starts_at=NOW,
        rules_snapshot={'mechanics_version': 'cycle_v1'})
    db.add(season)
    lands = {}
    for expected in _proposal():
        land = Territory(id=1000 + (77 - expected['source_id']) * 13,
            name=expected['name'], region='Тестовая карта', svg_path_data='M0 0 L1 1',
            is_playable=expected['is_playable'], has_port=expected['has_port'],
            stronghold_power=1 if expected['fortress'] else 0,
            resource_type=expected['profile_material'] or 'mithril',
            influence_value=expected['influence_value'], resource_wealth=98765,
            resource_output=1, secondary_resource_type='food')
        db.add(land)
        lands[land.name] = land
    db.flush()
    return season, lands


def _prepare(db, world, **kwargs):
    season, _ = world
    options = dict(season_id=season.id, catalog_version=VERSION, now=NOW)
    options.update(kwargs)
    return _catalog().prepare_income_profiles(db, **options)


def test_catalog_matches_every_proposed_row_and_remaps_ids(db, world):
    module = _catalog()
    assert module.INCOME_CATALOG_VERSION == VERSION
    actual = {entry.name: entry for entry in module.INCOME_CATALOG}
    assert len(module.INCOME_CATALOG) == len(actual) == 76
    for expected in _proposal():
        entry = actual[expected['name']]
        for field, value in expected.items():
            assert getattr(entry, field) == value, (entry.name, field)
    result = _prepare(db, world)
    assert result.catalog_version == VERSION
    assert len(result.profiles) == len(result.missing_territory_ids) == 75
    assert result.created_territory_ids == ()
    assert {entry.name for _, entry in result.profiles} == set(actual) - {'Тол-Фалас'}
    for territory_id, entry in result.profiles:
        assert territory_id == world[1][entry.name].id
        assert territory_id != entry.source_id
    assert db.query(CycleTerritoryProfile).count() == 0


def test_preview_executes_no_writes(db, world):
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.split()[0].upper())

    event.listen(db.get_bind(), 'before_cursor_execute', record)
    try:
        _prepare(db, world)
    finally:
        event.remove(db.get_bind(), 'before_cursor_execute', record)
    assert statements and set(statements) == {'SELECT'}


def test_apply_is_complete_idempotent_and_caller_can_rollback(db, world):
    result = _prepare(db, world, apply=True)
    assert len(result.created_territory_ids) == 75
    assert result.missing_territory_ids == ()
    assert CycleIncomeService().has_complete_profiles(db, season_id=world[0].id)
    profiles = db.query(CycleTerritoryProfile).all()
    assert len(profiles) == 75
    assert {p.revision for p in profiles} == {1}
    for territory_id, entry in result.profiles:
        row = db.get(CycleTerritoryProfile, (world[0].id, territory_id))
        assert Resources(**row.base) == entry.base
        assert row.profile_material == entry.profile_material
        assert set(row.base) == {'gold', 'iron', 'wood', 'food', 'mithril'}
    again = _prepare(db, world, apply=True)
    assert again.created_territory_ids == again.missing_territory_ids == ()
    assert {p.revision for p in profiles} == {1}
    db.rollback()
    assert db.query(CycleTerritoryProfile).count() == 0


@pytest.mark.parametrize('field,value,error', [
    ('name', 'Неизвестная земля', 'Неизвестная'),
    ('name', 'эвендим', 'Неизвестная'),
    ('is_playable', False, 'игровой статус'),
    ('has_port', True, 'порт'),
    ('stronghold_power', 1, 'крепость'),
    ('resource_type', 'wood', 'материал'),
    ('resource_output', 0, 'добыча'),
    ('influence_value', 999, 'влияние'),
])
def test_map_drift_blocks_all_profile_creation(db, world, field, value, error):
    setattr(world[1]['Эвендим'], field, value)
    db.flush()
    with pytest.raises(ValueError, match=error):
        _prepare(db, world, apply=True)
    assert db.query(CycleTerritoryProfile).count() == 0


def test_source_id_does_not_rescue_unknown_name(db, world):
    land = world[1]['Эвендим']
    land.id, land.name = 1, 'Другая карта'
    db.flush()
    with pytest.raises(ValueError, match='Неизвестная'):
        _prepare(db, world, apply=True)
    assert db.query(CycleTerritoryProfile).count() == 0


@pytest.mark.parametrize('playable', [True, False])
def test_unknown_extra_land_is_blocked_even_if_nonplayable(db, world, playable):
    db.add(Territory(name='Дополнительная земля', region='Тест', svg_path_data='',
                     is_playable=playable))
    db.flush()
    with pytest.raises(ValueError, match='Неизвестная'):
        _prepare(db, world, apply=True)
    assert db.query(CycleTerritoryProfile).count() == 0


def test_duplicate_name_is_ambiguous(db, world):
    world[1]['Рун'].name = 'Эвендим'
    db.flush()
    with pytest.raises(ValueError, match='Повтор'):
        _prepare(db, world, apply=True)
    assert db.query(CycleTerritoryProfile).count() == 0


@pytest.mark.parametrize('name', ['Эвендим', 'Тол-Фалас'])
def test_missing_catalog_land_blocks_partial_map(db, world, name):
    db.delete(world[1][name])
    db.flush()
    with pytest.raises(ValueError, match='Отсутствуют'):
        _prepare(db, world, apply=True)
    assert db.query(CycleTerritoryProfile).count() == 0


def test_empty_map_is_not_complete(db):
    season = CampaignSeason(number=1, name='Пустая карта', starts_at=NOW,
        rules_snapshot={'mechanics_version': 'cycle_v1'})
    db.add(season)
    db.flush()
    with pytest.raises(ValueError, match='Отсутствуют'):
        _prepare(db, (season, {}), apply=True)


def test_playable_tol_falas_is_blocked_without_fixing_map(db, world):
    land = world[1]['Тол-Фалас']
    land.is_playable = True
    db.flush()
    with pytest.raises(ValueError, match='игровой статус'):
        _prepare(db, world, apply=True)
    assert land.is_playable is True
    assert land.resource_type == 'mithril'
    assert db.query(CycleTerritoryProfile).count() == 0


@pytest.mark.parametrize('base,material', [
    ({'gold': '300', 'wood': '8', 'iron': '8'}, 'wood'),
    ({'gold': '450', 'wood': '8'}, 'wood'),
    ({'gold': '300', 'iron': '8'}, 'iron'),
    ({'gold': '300', 'wood': '8'}, None),
    ({'gold': '300', 'wood': '8', 'influence': '90'}, 'wood'),
    ({'gold': 'NaN', 'wood': '8'}, 'wood'),
    ({'gold': 300.0, 'wood': '8'}, 'wood'),
    (None, 'wood'),
])
def test_conflicting_profile_blocks_instead_of_overwriting(db, world, base, material):
    land = world[1]['Умбар']
    row = CycleTerritoryProfile(season_id=world[0].id, territory_id=land.id,
        base=base, profile_material=material)
    db.add(row)
    db.flush()
    with pytest.raises(ValueError, match='профиль'):
        _prepare(db, world, apply=True)
    assert db.query(CycleTerritoryProfile).count() == 1
    db.refresh(row)
    assert row.base == base and row.profile_material == material and row.revision == 1


@pytest.mark.parametrize('target', ['Тол-Фалас', None])
def test_profile_for_nonplayable_or_absent_land_blocks(db, world, target):
    territory_id = world[1][target].id if target else 999999
    db.add(CycleTerritoryProfile(season_id=world[0].id, territory_id=territory_id,
        base={'gold': '0'}, profile_material=None))
    db.flush()
    with pytest.raises(ValueError, match='профиль'):
        _prepare(db, world, apply=True)
    assert db.query(CycleTerritoryProfile).count() == 1


def test_matching_existing_profile_is_not_revised(db, world):
    land = world[1]['Умбар']
    row = CycleTerritoryProfile(season_id=world[0].id, territory_id=land.id,
        base={'gold': '300.00', 'wood': '8'}, profile_material='wood', revision=7)
    db.add(row)
    db.flush()
    result = _prepare(db, world, apply=True)
    assert len(result.created_territory_ids) == 74
    assert row.revision == 7 and row.base == {'gold': '300.00', 'wood': '8'}


def test_other_season_profiles_are_not_modified(db, world):
    other = CampaignSeason(number=2, name='Другой сезон', starts_at=NOW, status='scheduled',
        rules_snapshot={'mechanics_version': 'cycle_v1'})
    db.add(other)
    db.flush()
    row = CycleTerritoryProfile(season_id=other.id, territory_id=world[1]['Умбар'].id,
        base={'gold': '1'}, profile_material=None)
    db.add(row)
    db.flush()
    _prepare(db, world, apply=True)
    db.refresh(row)
    assert row.base == {'gold': '1'} and row.revision == 1


def test_stale_profile_identity_is_refreshed(db, world):
    _prepare(db, world, apply=True)
    row = db.get(CycleTerritoryProfile, (world[0].id, world[1]['Умбар'].id))
    db.execute(update(CycleTerritoryProfile).where(
        CycleTerritoryProfile.territory_id == row.territory_id).values(base={'gold': '1'})
        .execution_options(synchronize_session=False))
    assert row.base['gold'] == '300'
    with pytest.raises(ValueError, match='профиль'):
        _prepare(db, world)


def test_stale_map_identity_is_refreshed(db, world):
    land = world[1]['Эвендим']
    db.execute(update(Territory).where(Territory.id == land.id).values(has_port=True)
        .execution_options(synchronize_session=False))
    assert land.has_port is False
    with pytest.raises(ValueError, match='порт'):
        _prepare(db, world)


@pytest.mark.parametrize('options,error', [
    ({'catalog_version': 'v0'}, 'версия'),
    ({'catalog_version': None}, 'версия'),
    ({'season_id': 999999}, 'сезон'),
    ({'now': NOW.replace(tzinfo=None)}, 'часов'),
    ({'apply': 'yes'}, 'логическ'),
])
def test_invalid_context_blocks_writes(db, world, options, error):
    with pytest.raises((ValueError, TypeError), match=error):
        _prepare(db, world, **options)
    assert db.query(CycleTerritoryProfile).count() == 0


def test_legacy_season_is_not_accepted(db, world):
    world[0].rules_snapshot = {}
    db.flush()
    with pytest.raises(ValueError, match='cycle_v1'):
        _prepare(db, world, apply=True)


def test_pending_changes_are_not_implicitly_flushed(db, world):
    world[1]['Эвендим'].has_port = True
    with pytest.raises(ValueError, match='flush'):
        _prepare(db, world)
    with db.no_autoflush:
        assert db.execute(select(Territory.has_port).where(
            Territory.id == world[1]['Эвендим'].id)).scalar_one() is False


def test_started_preparation_blocks_apply_but_not_preview(db, world):
    db.add(CampaignCycleRecord(season_id=world[0].id, number=1, rule_version=1,
        starts_at=NOW - timedelta(days=3), preparation_at=NOW))
    db.flush()
    assert len(_prepare(db, world).missing_territory_ids) == 75
    with pytest.raises(ValueError, match='подготовк'):
        _prepare(db, world, apply=True)
    assert db.query(CycleTerritoryProfile).count() == 0


def test_existing_accrual_blocks_apply_atomically(db, world):
    clan = Clan(name='Получатель', created_at=NOW)
    db.add(clan)
    db.flush()
    state = CycleEconomyState(season_id=world[0].id, clan_id=clan.id,
        wallet={key: '0' for key in ('gold', 'iron', 'wood', 'food', 'mithril')})
    db.add(state)
    db.flush()
    db.add(CycleIncomeAccrual(state_id=state.id, accrued_through=NOW))
    db.flush()
    with pytest.raises(ValueError, match='начислен'):
        _prepare(db, world, apply=True)
    assert db.query(CycleTerritoryProfile).count() == 0


def test_late_insert_failure_rolls_back_all_created_profiles(db, world):
    statements = []

    def fail_second_insert(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO cycle_territory_profiles'):
            statements.append(statement)
            if len(statements) == 2:
                raise RuntimeError('Тестовый сбой второй вставки')

    event.listen(db.get_bind(), 'before_cursor_execute', fail_second_insert)
    try:
        with pytest.raises(RuntimeError, match='второй вставки'):
            _prepare(db, world, apply=True)
    finally:
        event.remove(db.get_bind(), 'before_cursor_execute', fail_second_insert)
    assert len(statements) == 2
    assert db.query(CycleTerritoryProfile).count() == 0
    assert db.query(Territory).count() == 76


def test_income_uses_single_umbar_profile_and_no_tol_falas_mithril(db, world):
    _prepare(db, world, apply=True)
    clan = Clan(name='Проверка доходов', created_at=NOW, base_influence=123,
        territory_points=213)
    db.add(clan)
    db.flush()
    for name in ('Умбар', 'Врата Мории', 'Перевал Карадрас'):
        land = world[1][name]
        land.owner_clan_id = clan.id
        db.add(TerritoryOwnershipHistory(territory_id=land.id, clan_id=clan.id,
                                        started_at=NOW))
    state = CycleEconomyState(season_id=world[0].id, clan_id=clan.id,
        wallet={key: '0' for key in ('gold', 'iron', 'wood', 'food', 'mithril')})
    db.add(state)
    db.flush()
    paid = CycleIncomeService().accrue(db, state_id=state.id, now=NOW + timedelta(days=1))
    assert paid == Resources(gold=650, iron=2, wood=10, food=2, mithril=2)
    assert clan.base_influence == 123 and clan.territory_points == 213
    assert db.get(CycleTerritoryProfile, (world[0].id, world[1]['Тол-Фалас'].id)) is None


def test_profile_lock_order_follows_existing_services(db, world):
    db.add(CampaignCycleRecord(season_id=world[0].id, number=1, rule_version=1,
        starts_at=NOW, preparation_at=NOW + timedelta(hours=72)))
    db.flush()
    locked = []

    def record(execute_state):
        statement = execute_state.statement
        if getattr(statement, '_for_update_arg', None) is not None:
            locked.extend(table.name for table in statement.get_final_froms())

    event.listen(db, 'do_orm_execute', record)
    try:
        _prepare(db, world, apply=True)
    finally:
        event.remove(db, 'do_orm_execute', record)
    assert locked[:3] == ['campaign_cycles', 'campaign_seasons', 'territories']
