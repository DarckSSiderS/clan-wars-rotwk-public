from datetime import timedelta
import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.time import as_utc
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.cycle_income import CycleTerritoryProfile
from app.models.cycle_economy import CycleEconomyState
from app.models.territory import Territory
from app.models.clan import Clan
from app.models.user import User
from app.models.role import Role
from tests.test_cycle_launch_preflight import seed, NOW


@pytest.fixture
def world(db):
    seed(db)
    from app.services.campaign_rule_service import CampaignRuleService
    CampaignRuleService().get_active(db)
    db.add(Role(id=1, name='admin'))
    db.add(User(id=1, username='Administrator', role_id=1, is_active=True))
    db.flush()
    clan = Clan(name='Клан', leader_id=1, gold=9876, territory_points=777)
    db.add(clan)
    db.flush()
    db.query(Territory).filter_by(name='Шир').one().owner_clan_id = clan.id
    db.commit()
    return clan.id


def service():
    try:
        return importlib.import_module('app.services.cycle_season_launch_service').CycleSeasonLaunchService()
    except ModuleNotFoundError:
        pytest.fail('Нет ручного старта нового сезона')


def launch(db, **changes):
    return service().start(db, actor_user_id=1, name='Новая кампания', command_id='launch-test',
                           previous_season_id=1, now=NOW + timedelta(days=1), **changes)


def test_manual_launch_prepares_full_map_wallets_and_72_hours_without_old_reset(db, world):
    report = launch(db)
    season = db.get(CampaignSeason, report['season_id'])
    cycle = db.get(CampaignCycleRecord, report['cycle_id'])
    assert season.rules_snapshot['mechanics_version'] == 'cycle_v1'
    assert as_utc(cycle.preparation_at) - as_utc(season.starts_at) == timedelta(hours=72)
    assert db.query(CycleTerritoryProfile).count() == 75
    assert db.query(CycleEconomyState).one().wallet['gold'] == '1000'
    assert db.get(Clan, world).gold == 9876
    assert db.get(Clan, world).territory_points == 50
    assert db.get(Clan, world).base_influence == 0
    assert db.query(Territory).filter_by(name='Шир').one().owner_clan_id == world
    assert db.query(Territory).filter_by(name='Тол-Фалас').one().is_playable is False
    assert db.get(CampaignSeason, 1).status == 'completed'
    db.rollback()
    assert db.query(CampaignSeason).count() == 1
    assert db.query(CampaignCycleRecord).count() == 0
    assert db.query(Territory).filter_by(name='Тол-Фалас').one().is_playable is True


def test_same_command_is_idempotent_but_another_start_is_rejected(db, world):
    first = launch(db)
    db.commit()
    assert launch(db) == first
    with pytest.raises(ValueError):
        service().start(db, actor_user_id=1, name='Лишняя', command_id='another', previous_season_id=1, now=NOW)
    assert db.query(CampaignSeason).count() == 2


def test_unknown_map_rolls_back_every_part_of_launch(db, world):
    db.add(Territory(name='Лишняя земля', region='Пример', svg_path_data='M0 0'))
    db.commit()
    with pytest.raises(ValueError, match='каталога'):
        launch(db)
    assert db.query(CampaignSeason).count() == 1
    assert db.query(CycleTerritoryProfile).count() == 0
    assert db.query(CycleEconomyState).count() == 0
    assert db.query(Territory).filter_by(name='Тол-Фалас').one().is_playable is True


def test_preparation_is_read_only_and_exposes_next_balance_not_old_upgrades(db, world):
    land = db.query(Territory).filter_by(name='Шир').one()
    land.development_level = 9
    land.influence_value = 777
    db.commit()
    result = service().preparation(db)
    row = next(row for row in result['territories'] if row['territory_id'] == land.id)
    assert row['daily_income']['gold'] == '200'
    assert row['influence_value'] == 50
    assert row['levels']['gold'] == 0
    assert row['max_level'] == 3
    assert land.influence_value == 777 and land.development_level == 9
    assert db.query(CampaignSeason).count() == 1
    assert not db.new and not db.dirty


def test_launch_requires_admin_and_refuses_running_wars(db, world):
    with pytest.raises(PermissionError):
        service().start(db, actor_user_id=999, name='Нет', command_id='no', previous_season_id=1, now=NOW)
    from app.models.war import ClanWar
    land = db.query(Territory).first()
    db.add(ClanWar(attacking_clan_id=world, territory_id=land.id, war_type='conquest', status='active'))
    db.commit()
    with pytest.raises(ValueError, match='битв'):
        launch(db)
    assert db.query(CampaignSeason).count() == 1


def test_public_read_cannot_launch_and_legacy_reset_is_not_the_new_entry(db, world):
    from app.api.v1.campaign import router
    from app.database import get_db
    site = FastAPI()
    site.include_router(router)
    site.dependency_overrides[get_db] = lambda: db
    client = TestClient(site)
    assert client.get('/campaign/map/preparation').status_code == 200
    assert client.post('/campaign/seasons/start', json={'name': 'Новая', 'command_id': 'x', 'previous_season_id': 1}).status_code == 401
    assert db.query(CampaignSeason).count() == 1


def test_failure_after_income_creation_leaves_no_partial_launch(db, world, monkeypatch):
    from app.services.cycle_startup_service import CycleStartupService
    def failed(*args, **kwargs):
        raise ValueError('Проверка отката')
    monkeypatch.setattr(CycleStartupService, 'qualify', failed)
    with pytest.raises(ValueError, match='отката'):
        launch(db)
    assert db.query(CampaignSeason).count() == 1
    assert db.query(CycleTerritoryProfile).count() == 0
    assert db.query(CycleEconomyState).count() == 0
    assert db.query(Territory).filter_by(name='Тол-Фалас').one().is_playable is True


def test_starting_triple_and_expiry_recalculate_new_influence(db, world):
    from app.services.cycle_startup_service import CycleStartupService
    lands = [db.query(Territory).filter_by(name=name).one() for name in ('Шир', 'Эвендим', 'Арнор')]
    for land in lands:
        land.adjacent_territory_ids = [other.id for other in lands if other.id != land.id]
    db.commit()
    report = launch(db)
    CycleStartupService().claim(db, cycle_id=report['cycle_id'], clan_id=world, actor_id=1,
                               selected=[land.id for land in lands], now=NOW + timedelta(days=1, hours=1))
    assert db.get(Clan, world).territory_points == 150
    db.rollback()
    report = launch(db)
    CycleStartupService().expire(db, cycle_id=report['cycle_id'], now=NOW + timedelta(days=4))
    assert db.get(Clan, world).territory_points == 0


def test_parallel_manual_starts_create_one_season(postgres_db):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    from app.services.campaign_rule_service import CampaignRuleService
    db = postgres_db
    seed(db)
    db.add(User(id=1, username='Admin', role_id=1, is_active=True))
    CampaignRuleService().get_active(db)
    db.commit()
    engine, barrier = db.bind, Barrier(2)
    def attempt(command):
        with Session(engine) as session:
            barrier.wait(timeout=10)
            try:
                value = service().start(session, actor_user_id=1, name='Новый сезон', command_id=command,
                                        previous_season_id=1, now=NOW)
                session.commit()
                return value['season_id']
            except ValueError:
                session.rollback()
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, command) for command in ('one', 'two')]
        results = [future.result(timeout=30) for future in futures]
    assert sum(result is not None for result in results) == 1
    assert db.query(CampaignSeason).count() == 2
    assert db.query(CampaignCycleRecord).count() == 1
