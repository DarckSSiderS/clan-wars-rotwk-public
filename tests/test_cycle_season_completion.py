from datetime import timedelta

import pytest

from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.campaign_history_service import CampaignHistoryService
from tests.test_campaign_cycle_store import season, prepare
from app.models.clan import Clan
from app.models.territory import Territory


def test_existing_completion_service_cannot_bypass_pending_new_cycle(db):
    owner = season(db)
    CampaignCycleStore().start(db, season_id=owner.id)
    with pytest.raises(ValueError, match='cycle'):
        CampaignHistoryService().complete_active_season(db)
    assert owner.status == 'active'


def test_season_end_waits_for_manual_request_and_final_calculation(db):
    owner = season(db)
    service = CampaignCycleStore()
    cycle = service.start(db, season_id=owner.id)
    prepare(db, cycle)
    deadline = service.timeline(cycle).replay_deadline
    service.mark_import_complete(db, cycle_id=cycle.id, verified_at=deadline)
    service.settle(db, cycle_id=cycle.id, completed_at=deadline)
    with pytest.raises(ValueError):
        CampaignHistoryService().complete_active_season(db, completed_at=deadline + timedelta(hours=1))
    service.request_end(db, cycle_id=cycle.id)
    result = CampaignHistoryService().complete_active_season(db, completed_at=deadline + timedelta(hours=1))
    assert result.status == 'completed'


def test_new_season_ranking_uses_held_land_not_base_and_keeps_shared_rank(db):
    owner = season(db)
    first = Clan(name='A', base_influence=100, territory_points=999)
    second = Clan(name='B', base_influence=500, territory_points=1000)
    db.add_all([first, second])
    db.flush()
    for clan in (first, second):
        db.add(Territory(name=clan.name, region='test', svg_path_data='', owner_clan_id=clan.id, influence_value=50))
    db.flush()
    service = CampaignCycleStore()
    cycle = service.start(db, season_id=owner.id)
    prepare(db, cycle)
    deadline = service.timeline(cycle).replay_deadline
    service.mark_import_complete(db, cycle_id=cycle.id, verified_at=deadline)
    service.request_end(db, cycle_id=cycle.id)
    service.settle(db, cycle_id=cycle.id, completed_at=deadline)
    CampaignHistoryService().complete_active_season(db, completed_at=deadline)
    db.flush()
    from app.models.campaign import CampaignSeasonClanResult
    rows = db.query(CampaignSeasonClanResult).all()
    assert [r.influence for r in rows] == [50, 50]
    assert [r.rank for r in rows] == [1, 1]
