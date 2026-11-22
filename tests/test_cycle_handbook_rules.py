from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.v1.campaign import router
from app.database import get_db
from app.models.campaign import CampaignSeason
from app.services.campaign_history_service import CampaignHistoryService
from app.services.campaign_rule_service import CampaignRuleService
from app.core.time import utc_now


def season(db, number, mode=None, status='active'):
    rules = CampaignRuleService().get_active(db)
    snapshot = dict(version=rules.version, rule_set_id=rules.id, values=dict(rules.values),
                    orders=[{'kind': 'ambush', 'user_id': 987}], reserve=[456])
    if mode is not None:
        snapshot['mechanics_version'] = mode
    row = CampaignSeason(number=number, name=f'Сезон {number}', status=status,
                         starts_at=utc_now(), starting_influence=100,
                         reset_development=True, rules_snapshot=snapshot)
    db.add(row)
    db.flush()
    return row


@pytest.mark.parametrize('explicit', [False, True])
def test_public_rules_confirm_cycle_mode_without_exposing_secret_orders(db, explicit):
    row = season(db, 1, 'cycle_v1')
    before = deepcopy(row.rules_snapshot)
    result = CampaignHistoryService().public_rules_snapshot(db, season_id=row.id if explicit else None)
    assert result['mechanics_version'] == 'cycle_v1'
    assert set(result) == {'mechanics_version', 'rule_set', 'season'}
    assert 'orders' not in result['season']
    assert 'reserve' not in result['rule_set']
    assert row.rules_snapshot == before


@pytest.mark.parametrize('mode', [None, 'legacy', 'cycle_v2'])
def test_selected_legacy_or_unknown_season_never_inherits_active_cycle_mode(db, mode):
    old = season(db, 1, mode, status='completed')
    season(db, 2, 'cycle_v1')
    result = CampaignHistoryService().public_rules_snapshot(db, season_id=old.id)
    assert result['mechanics_version'] is None
    assert result['season']['id'] == old.id


def test_archived_cycle_rules_remain_selectable_without_an_active_season(db):
    archived = season(db, 1, 'cycle_v1', status='completed')
    service = CampaignHistoryService()
    assert service.public_rules_snapshot(db, season_id=archived.id)['mechanics_version'] == 'cycle_v1'
    assert service.public_rules_snapshot(db)['mechanics_version'] is None
    assert service.public_rules_snapshot(db, season_id=999999) is None


def test_public_endpoint_exposes_only_mode_of_requested_season(db):
    old = season(db, 1, status='completed')
    active = season(db, 2, 'cycle_v1')
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        response = client.get('/api/v1/campaign/rules/public')
        assert response.status_code == 200
        payload = response.json()
        assert payload['mechanics_version'] == 'cycle_v1'
        assert payload['season']['id'] == active.id
        assert set(payload) == {'rule_set', 'season', 'mechanics_version'}
        assert 'ambush' not in response.text
        assert 'reserve' not in response.text
        response = client.get(f'/api/v1/campaign/rules/public?season_id={old.id}')
        assert response.status_code == 200
        assert response.json()['mechanics_version'] is None
        assert response.json()['season']['id'] == old.id
        assert client.get('/api/v1/campaign/rules/public?season_id=999999').status_code == 404
