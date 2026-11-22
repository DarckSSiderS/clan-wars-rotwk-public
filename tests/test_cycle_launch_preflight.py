from datetime import datetime, timezone

import pytest

from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.cycle_income import CycleTerritoryProfile
from app.models.territory import Territory
from tests.test_cycle_income_catalog import _proposal


NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)


def seed(db):
    old = CampaignSeason(number=1, name='Прежний сезон', starts_at=NOW, status='completed',
        rules_snapshot={'mechanics_version': 'legacy', 'version': 2})
    db.add(old)
    for entry in _proposal():
        db.add(Territory(name=entry['name'], region='Приёмка', svg_path_data='M0 0 L1 1',
            is_playable=True, has_port=entry['has_port'],
            stronghold_power=1 if entry['fortress'] else 0,
            influence_value=entry['influence_value'], resource_type=entry['profile_material'] or 'mithril',
            resource_output=1))
    db.flush()


def test_preflight_checks_all_profiles_and_startup_without_persisting_season(db):
    from app.services.cycle_launch_preflight import preview_preparation
    seed(db)
    report = preview_preparation(db, now=NOW)
    assert report['playable_territories'] == report['income_profiles'] == 75
    assert report['registration_hours'] == 72
    assert report['changes_rolled_back'] is True
    assert report['map_adjustments'] == [{'name': 'Тол-Фалас', 'is_playable': False}]
    assert db.query(CampaignSeason).count() == 1
    assert db.query(CampaignCycleRecord).count() == 0
    assert db.query(CycleTerritoryProfile).count() == 0


def test_preflight_does_not_finish_existing_active_season(db):
    from app.services.cycle_launch_preflight import preview_preparation
    seed(db)
    previous = db.query(CampaignSeason).one()
    previous.status = 'active'
    db.flush()
    with pytest.raises(ValueError, match='вручную'):
        preview_preparation(db, now=NOW)
    assert previous.status == 'active'
    assert db.query(CampaignSeason).count() == 1
    assert db.query(Territory).filter_by(name='Тол-Фалас').one().is_playable is True


def test_preflight_unknown_map_fails_without_leftover_season(db):
    from app.services.cycle_launch_preflight import preview_preparation
    seed(db)
    db.add(Territory(name='Неизвестная земля', region='Приёмка', svg_path_data='M0 0'))
    db.flush()
    with pytest.raises(ValueError, match='Неизвестная земля'):
        preview_preparation(db, now=NOW)
    assert db.query(CampaignSeason).count() == 1
    assert db.query(CampaignCycleRecord).count() == 0
    assert db.query(CycleTerritoryProfile).count() == 0
