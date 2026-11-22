from copy import deepcopy

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
import pytest

from app.api.v1.campaign import router
from app.database import get_db
from app.models.campaign import CampaignSeason, CampaignSettings
from app.models.campaign_cycle import CampaignCycleRecord
from app.services.campaign_history_service import CampaignHistoryService
from app.services.campaign_rule_service import CampaignRuleService
from tests.test_cycle_handbook_rules import season


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as instance:
        yield instance


@pytest.mark.parametrize('mode', [None, 'legacy', 'cycle_v1'])
def test_default_interseason_decorates_guide_without_changing_actual_context(db, client, mode):
    previous = season(db, 1, mode, status='completed')
    snapshot = deepcopy(previous.rules_snapshot)
    actual = CampaignHistoryService().public_rules_snapshot(db)
    response = client.get('/api/v1/campaign/rules/public')
    assert response.status_code == 200
    payload = response.json()
    assert payload.pop('guide', None) == {
        'mechanics_version': 'cycle_v1', 'status': 'upcoming',
        'previous_season_id': previous.id,
    }
    assert payload == jsonable_encoder(actual)
    db.flush()
    db.expire_all()
    assert previous.rules_snapshot == snapshot
    assert previous.status == 'completed'
    assert db.query(CampaignSeason).count() == 1
    assert db.query(CampaignCycleRecord).count() == 0
    assert db.query(CampaignSettings).count() == 0


@pytest.mark.parametrize('mode', [None, 'cycle_v1'])
@pytest.mark.parametrize('explicit', [False, True])
def test_active_season_payload_is_unchanged(db, client, mode, explicit):
    season(db, 1, status='completed')
    active = season(db, 2, mode)
    selected = active.id if explicit else None
    actual = CampaignHistoryService().public_rules_snapshot(db, season_id=selected)
    response = client.get('/api/v1/campaign/rules/public',
                          params={'season_id': selected} if explicit else {})
    assert response.status_code == 200
    assert response.json() == jsonable_encoder(actual)
    assert 'guide' not in response.json()


@pytest.mark.parametrize('mode', [None, 'cycle_v1'])
def test_explicit_history_never_receives_upcoming_guide(db, client, mode):
    previous = season(db, 1, mode, status='completed')
    actual = CampaignHistoryService().public_rules_snapshot(db, season_id=previous.id)
    response = client.get('/api/v1/campaign/rules/public', params={'season_id': previous.id})
    assert response.status_code == 200
    assert response.json() == jsonable_encoder(actual)
    assert 'guide' not in response.json()


def test_latest_completed_season_is_guide_predecessor(db, client):
    season(db, 1, status='completed')
    latest = season(db, 3, status='completed')
    payload = client.get('/api/v1/campaign/rules/public').json()
    assert payload.get('guide', {}).get('previous_season_id') == latest.id


@pytest.mark.parametrize('status', [None, 'scheduled', 'finished'])
def test_bootstrap_and_non_interseason_payload_have_no_guide(db, client, status):
    CampaignRuleService().get_active(db)
    if status:
        season(db, 1, status='completed')
        season(db, 2, status=status)
    actual = CampaignHistoryService().public_rules_snapshot(db)
    response = client.get('/api/v1/campaign/rules/public')
    assert response.status_code == 200
    assert response.json() == jsonable_encoder(actual)
    assert 'guide' not in response.json()


def test_public_errors_stay_errors_and_do_not_create_season(db, client):
    assert client.get('/api/v1/campaign/rules/public').status_code == 503
    assert client.get('/api/v1/campaign/rules/public?season_id=99999').status_code == 404
    assert client.get('/api/v1/campaign/rules/public?season_id=0').status_code == 422
    assert db.query(CampaignSeason).count() == 0
