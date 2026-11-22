from datetime import timedelta
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.cycle_economy import router
from app.core.auth import get_current_active_user
from app.database import get_db
from tests.test_cycle_plan_service import setup_world
from tests.test_campaign_cycle_store import START
from app.models.cycle_economy import CycleEconomyState
from app.models.cycle_income import CycleIncomeAccrual
from app.models.territory import TerritoryOwnershipHistory
from app.services.cycle_economy import Resources
from app.services.cycle_income_service import CycleIncomeService


def economy_world(db, monkeypatch):
    users, clan, land, cycle = setup_world(db)
    clan.created_at = START
    db.add(TerritoryOwnershipHistory(territory_id=land.id, clan_id=clan.id, started_at=START))
    db.flush()
    CycleIncomeService().configure_profile(db, season_id=cycle.season_id, territory_id=land.id,
        base=Resources(100, 4), profile_material='iron', now=START)
    monkeypatch.setattr('app.api.v1.cycle_economy.utc_now', lambda: START)
    return users, clan, land, cycle


def client_for(db, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: user
    return TestClient(app)


def test_initial_wallet_once_and_private_read(db, monkeypatch):
    users, clan, _, cycle = economy_world(db, monkeypatch)
    url = f'/economy/seasons/{cycle.season_id}/clans/{clan.id}'
    client = client_for(db, users[0])
    first = client.post(url + '/initialize').json()
    assert first['wallet']['gold'] == '1000'
    assert client.post(url + '/initialize').json()['state_id'] == first['state_id']
    assert client_for(db, users[2]).get(url).status_code == 200
    assert client_for(db, users[3]).get(url).status_code == 403


def test_starter_selection_is_once_only_and_market_requires_head_or_trader(db, monkeypatch):
    users, clan, _, cycle = economy_world(db, monkeypatch)
    url = f'/economy/seasons/{cycle.season_id}/clans/{clan.id}'
    client = client_for(db, users[0])
    state = client.post(url + '/initialize').json()
    response = client.post(url + '/starters', json={'expected_revision': state['revision'],
                                                  'selected': ['royal_charter', 'white_tree']})
    assert response.status_code == 200
    assert response.json()['starters_chosen'] is True
    revision = response.json()['revision']
    assert client.post(url + '/starters', json={'expected_revision': revision,
                                               'selected': ['royal_charter', 'white_tree']}).status_code == 409
    payload = {'expected_revision': revision, 'resource': 'wood', 'quantity': '1', 'buying': True}
    assert client_for(db, users[2]).post(url + '/market', json=payload).status_code == 403
    assert client.post(url + '/market', json=payload).status_code == 200


def test_loadout_change_accrues_old_rates_and_read_credits_new_rates_once(db, monkeypatch):
    users, clan, _, cycle = economy_world(db, monkeypatch)
    url = f'/economy/seasons/{cycle.season_id}/clans/{clan.id}'
    client = client_for(db, users[0])
    state = client.post(url + '/initialize').json()
    state = client.post(url + '/starters', json={'expected_revision': state['revision'],
        'selected': ['royal_charter', 'white_tree']}).json()
    monkeypatch.setattr('app.api.v1.cycle_economy.utc_now', lambda: START + timedelta(days=3))
    response = client.put(url + '/active-relics', json={'cycle_id': cycle.id,
        'selected': ['white_tree'], 'expected_revision': state['revision']})
    assert response.status_code == 200, response.text
    assert Decimal(response.json()['wallet']['gold']) == 1600
    monkeypatch.setattr('app.api.v1.cycle_economy.utc_now', lambda: START + timedelta(days=3, hours=12))
    updated = client.get(url)
    assert updated.status_code == 200, updated.text
    assert Decimal(updated.json()['wallet']['gold']) == Decimal('1707.5')
    assert client.get(url).json() == updated.json()


def test_failed_purchase_rolls_back_income_and_stale_revision_cannot_spend(db, monkeypatch):
    users, clan, _, cycle = economy_world(db, monkeypatch)
    url = f'/economy/seasons/{cycle.season_id}/clans/{clan.id}'
    client = client_for(db, users[0])
    initial = client.post(url + '/initialize').json()
    monkeypatch.setattr('app.api.v1.cycle_economy.utc_now', lambda: START + timedelta(days=1))
    rejected = client.post(url + '/market', json={'expected_revision': initial['revision'],
        'resource': 'mithril', 'quantity': '9999', 'buying': True})
    assert rejected.status_code == 409
    state = db.get(CycleEconomyState, initial['state_id'], populate_existing=True)
    assert Decimal(state.wallet['gold']) == 1000
    assert db.get(CycleIncomeAccrual, state.id) is None
    current = client.get(url).json()
    assert Decimal(current['wallet']['gold']) == 1200
    rejected = client.post(url + '/market', json={'expected_revision': initial['revision'],
        'resource': 'wood', 'quantity': '1', 'buying': True})
    assert rejected.status_code == 409
    assert client.get(url).json() == current
