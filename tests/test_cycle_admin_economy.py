from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.database import get_db
from app.main import app
from app.models.campaign import CampaignSeason
from app.models.cycle_economy import CycleEconomySnapshot, CycleEconomyState
from app.models.cycle_income import CycleIncomeAccrual
from app.models.operation import AdminAuditLog
from app.models.role import Role
from app.models.territory import TerritoryOwnershipHistory
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_economy import Resources
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_income_service import CycleIncomeService
from tests.test_campaign_cycle_store import START
from tests.test_cycle_plan_service import setup_world


@pytest.fixture
def world(db, monkeypatch):
    users, clan, land, cycle = setup_world(db)
    admin = Role(id=1, name='admin')
    member = Role(id=2, name='user')
    db.add_all([admin, member])
    users[0].role = admin
    users[1].role = admin
    users[2].role = member
    clan.created_at = START
    clan.gold, clan.iron = 777, 13
    db.add(TerritoryOwnershipHistory(territory_id=land.id, clan_id=clan.id, started_at=START))
    db.flush()
    CycleIncomeService().configure_profile(db, season_id=cycle.season_id, territory_id=land.id,
        base=Resources(100, 4), profile_material='iron', now=START)
    state = CycleEconomyStore().ensure_state(db, season_id=cycle.season_id, clan_id=clan.id)
    db.commit()
    # Patch only the clock; all database operations use conftest's in-memory db.
    from app.core import time as clock
    monkeypatch.setattr(clock, 'utc_now', lambda: START)
    yield users, clan, cycle, state
    app.dependency_overrides.clear()


def client_for(db, user):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: user
    return TestClient(app)


def url(clan):
    return f'/api/v1/admin/clans/{clan.id}/cycle-economy'


def test_admin_clan_table_uses_the_same_seasonal_treasury_as_editor(db, world):
    users, clan, cycle, state = world
    client = client_for(db, users[0])
    rows = client.get('/api/v1/admin/clans').json()['clans']
    row = next(row for row in rows if row['id'] == clan.id)
    assert row['gold'] == state.wallet['gold']
    assert row['iron'] == state.wallet['iron']
    season = db.get(CampaignSeason, cycle.season_id)
    season.rules_snapshot = {'mechanics_version': 'legacy'}
    db.commit()
    legacy = next(row for row in client.get('/api/v1/admin/clans').json()['clans'] if row['id'] == clan.id)
    assert legacy['gold'] == 777 and legacy['iron'] == 13


def test_old_admin_endpoint_cannot_silently_change_legacy_wallet_in_cycle_mode(db, world):
    users, clan, _, _ = world
    response = client_for(db, users[0]).patch(f'/api/v1/admin/clans/{clan.id}/economy',
        json={'gold': 123, 'reason': 'Проверка старого запроса'})
    assert response.status_code == 409
    db.refresh(clan)
    assert clan.gold == 777


def command(cycle, state, **changes):
    return dict(season_id=cycle.season_id, expected_revision=state.revision,
                command_id='admin-treasury-1', reason='Restore verified treasury',
                wallet={'gold': '1234.125', 'iron': '42', 'wood': '30', 'food': '20', 'mithril': '5'},
                **changes)


def test_loads_current_season_wallet_not_legacy_and_audits_correction(db, world):
    users, clan, cycle, state = world
    client = client_for(db, users[0])
    response = client.get(url(clan))
    assert response.status_code == 200, response.text
    current = response.json()
    assert current['mechanics_version'] == 'cycle_v1'
    assert current['state']['wallet']['gold'] == '1000'
    assert current['state']['revision'] == 1
    result = client.patch(url(clan), json=command(cycle, state))
    assert result.status_code == 200, result.text
    assert result.json()['wallet']['gold'] == '1234.125'
    assert result.json()['revision'] == 2
    db.refresh(clan)
    assert (clan.gold, clan.iron) == (777, 13)
    audit = db.query(AdminAuditLog).one()
    assert audit.actor_user_id == users[0].id
    assert audit.reason == 'Restore verified treasury'
    assert audit.before_data['wallet']['gold'] == '1000'
    assert audit.after_data['wallet']['gold'] == '1234.125'
    assert audit.after_data['season_id'] == cycle.season_id
    assert audit.after_data['clan_id'] == clan.id


@pytest.mark.parametrize('method', ['get', 'patch'])
def test_only_admin_can_read_or_correct_treasury(db, world, method):
    users, clan, cycle, state = world
    client = client_for(db, users[2])
    kwargs = {'json': command(cycle, state)} if method == 'patch' else {}
    assert getattr(client, method)(url(clan), **kwargs).status_code == 403
    assert db.query(AdminAuditLog).count() == 0


def test_stale_revision_is_conflict_without_side_effects(db, world):
    users, clan, cycle, state = world
    payload = command(cycle, state)
    payload['expected_revision'] = 99
    result = client_for(db, users[0]).patch(url(clan), json=payload)
    assert result.status_code == 409, result.text
    db.refresh(state)
    assert state.wallet['gold'] == '1000'
    assert state.revision == 1
    assert db.query(AdminAuditLog).count() == 0
    assert db.query(CycleIncomeAccrual).count() == 0


def test_committed_retry_returns_original_result_even_after_other_correction(db, world):
    users, clan, cycle, state = world
    payload = command(cycle, state)
    client = client_for(db, users[0])
    first = client.patch(url(clan), json=payload)
    assert first.status_code == 200, first.text
    second_payload = deepcopy(payload)
    second_payload.update(command_id='admin-treasury-2', expected_revision=2)
    second_payload['wallet']['gold'] = '2000'
    assert client.patch(url(clan), json=second_payload).status_code == 200
    with Session(db.get_bind()) as fresh:
        actor = fresh.get(type(users[0]), users[0].id)
        retry = client_for(fresh, actor).patch(url(clan), json=payload)
        assert retry.status_code == 200, retry.text
        assert retry.json() == first.json()
        assert fresh.query(AdminAuditLog).count() == 2
        assert fresh.get(CycleEconomyState, state.id).wallet['gold'] == '2000'


def test_equivalent_decimal_spelling_retries_the_same_command(db, world):
    users, clan, cycle, state = world
    payload = command(cycle, state)
    payload['wallet']['gold'] = '1234.1250'
    client = client_for(db, users[0])
    first = client.patch(url(clan), json=payload)
    assert first.status_code == 200, first.text
    payload['wallet']['gold'] = '1234.125'
    repeated = client.patch(url(clan), json=payload)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == first.json()
    assert db.query(AdminAuditLog).count() == 1


@pytest.mark.parametrize('change', ['wallet', 'reason', 'revision', 'actor', 'clan'])
def test_command_key_cannot_be_reused_for_different_request(db, world, change):
    users, clan, cycle, state = world
    payload = command(cycle, state)
    client = client_for(db, users[0])
    assert client.patch(url(clan), json=payload).status_code == 200
    target = url(clan)
    if change == 'wallet':
        payload['wallet']['gold'] = '2222'
    elif change == 'reason':
        payload['reason'] = 'Different reason'
    elif change == 'revision':
        payload['expected_revision'] = 2
    elif change == 'actor':
        client = client_for(db, users[1])
    else:
        from app.models.clan import Clan
        other = Clan(name='Other', leader_id=users[1].id, created_at=START)
        db.add(other)
        db.flush()
        CycleEconomyStore().ensure_state(db, season_id=cycle.season_id, clan_id=other.id)
        db.commit()
        target = url(other)
    assert client.patch(target, json=payload).status_code == 409
    assert db.query(AdminAuditLog).count() == 1


@pytest.mark.parametrize('field,value', [
    ('reason', '  '), ('reason', 'ab'), ('command_id', ''),
    ('expected_revision', 0), ('expected_revision', True),
    ('wallet', {'gold': '-1'}), ('wallet', {'gold': 'NaN'}),
    ('wallet', {'gold': 'Infinity'}), ('wallet', {'gold': 1.25}),
    ('wallet', {'gold': True}), ('wallet', {'gold': '1', 'influence': '2'}),
])
def test_invalid_input_does_not_mutate_wallet(db, world, field, value):
    users, clan, cycle, state = world
    payload = command(cycle, state)
    payload[field] = value
    result = client_for(db, users[0]).patch(url(clan), json=payload)
    assert result.status_code == 422, result.text
    assert db.query(AdminAuditLog).count() == 0
    db.refresh(state)
    assert state.revision == 1


@pytest.mark.parametrize('mode', ['legacy', 'completed', 'wrong_season', 'missing_state'])
def test_correction_requires_current_active_cycle_season_and_existing_wallet(db, world, mode):
    users, clan, cycle, state = world
    payload = command(cycle, state)
    season = db.get(CampaignSeason, cycle.season_id)
    if mode == 'legacy':
        season.rules_snapshot = {'mechanics_version': 'legacy'}
    elif mode == 'completed':
        season.status = 'completed'
    elif mode == 'wrong_season':
        payload['season_id'] += 1
    else:
        db.delete(state)
    db.commit()
    result = client_for(db, users[0]).patch(url(clan), json=payload)
    assert result.status_code == 409, result.text
    assert db.query(AdminAuditLog).count() == 0


def test_legacy_mode_is_explicit_and_read_does_not_initialize_season_wallet(db, world):
    users, clan, cycle, state = world
    db.get(CampaignSeason, cycle.season_id).rules_snapshot = {'mechanics_version': 'legacy'}
    db.delete(state)
    db.commit()
    result = client_for(db, users[0]).get(url(clan))
    assert result.status_code == 200, result.text
    assert result.json()['mechanics_version'] == 'legacy'
    assert result.json()['state'] is None
    assert db.query(CycleEconomyState).count() == 0


def test_read_accrues_actual_income_before_loading_revision(db, world, monkeypatch):
    users, clan, _, state = world
    monkeypatch.setattr('app.core.time.utc_now', lambda: START + timedelta(days=1))
    response = client_for(db, users[0]).get(url(clan))
    assert response.status_code == 200, response.text
    assert Decimal(response.json()['state']['wallet']['gold']) == Decimal('1200')
    assert response.json()['state']['revision'] == 2
    assert client_for(db, users[0]).get(url(clan)).json() == response.json()


def test_correction_never_changes_frozen_battle_snapshot(db, world, monkeypatch):
    users, clan, cycle, state = world
    battle_at = CampaignCycleStore.timeline(cycle).battle_at
    snapshot = CycleEconomyStore().freeze_snapshot(db, state_id=state.id, cycle_id=cycle.id,
        now=battle_at, expected_revision=state.revision)
    before = (deepcopy(snapshot.effects), deepcopy(snapshot.territory_upgrades), snapshot.state_revision)
    db.commit()
    monkeypatch.setattr('app.core.time.utc_now', lambda: battle_at)
    response = client_for(db, users[0]).patch(url(clan), json=command(cycle, state))
    assert response.status_code == 200, response.text
    db.refresh(snapshot)
    assert (snapshot.effects, snapshot.territory_upgrades, snapshot.state_revision) == before
    assert db.query(CycleEconomySnapshot).count() == 1


def test_missing_reveal_snapshot_blocks_correction_and_rolls_back(db, world, monkeypatch):
    users, clan, cycle, state = world
    monkeypatch.setattr('app.core.time.utc_now', lambda: CampaignCycleStore.timeline(cycle).battle_at)
    result = client_for(db, users[0]).patch(url(clan), json=command(cycle, state))
    assert result.status_code == 409, result.text
    db.refresh(state)
    assert state.wallet['gold'] == '1000'
    assert db.query(CycleIncomeAccrual).count() == 0
    assert db.query(AdminAuditLog).count() == 0


def test_audit_failure_rolls_back_wallet_and_income(db, world, monkeypatch):
    users, clan, cycle, state = world
    from app.services.operation_service import AdminAuditService

    def fail(*args, **kwargs):
        raise RuntimeError('test audit failure')

    monkeypatch.setattr(AdminAuditService, 'record', fail)
    monkeypatch.setattr('app.core.time.utc_now', lambda: START + timedelta(days=1))
    with pytest.raises(RuntimeError, match='test audit failure'):
        client_for(db, users[0]).patch(url(clan), json=command(cycle, state))
    db.refresh(state)
    assert state.wallet['gold'] == '1000'
    assert state.revision == 1
    assert db.query(CycleIncomeAccrual).count() == 0
    assert db.query(AdminAuditLog).count() == 0
