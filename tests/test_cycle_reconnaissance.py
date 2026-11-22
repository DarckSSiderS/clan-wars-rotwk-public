from datetime import timedelta

import pytest

from app.models.campaign_cycle import CampaignCyclePlan, CampaignCyclePlanRevision
from app.models.clan import Clan
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_plan_service import CyclePlanService
from app.services.cycle_reconnaissance_service import CycleReconnaissanceService
from app.services.cycle_orders import Order
from tests.test_cycle_plan_service import setup_world


def test_plan_history_keeps_immutable_revisions_for_a_delayed_scout_report(db):
    users, clan, land, cycle = setup_world(db)
    timeline = CampaignCycleStore.timeline(cycle)
    service = CyclePlanService()
    service.capture_preparation(db, cycle_id=cycle.id, now=timeline.preparation_at)
    service.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
                 orders=[Order(users[2].id, 'defend', land.id)], expected_revision=0, now=timeline.preparation_at)
    service.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
                 orders=[], expected_revision=1, now=timeline.preparation_at + timedelta(hours=1))
    rows = db.query(CampaignCyclePlanRevision).order_by(CampaignCyclePlanRevision.revision).all()
    assert len(rows) == 2
    assert len(rows[0].orders) == 1
    assert rows[1].orders == []


def test_scout_cost_is_once_only_target_is_immutable_and_report_is_anonymous(db):
    users, clan, land, cycle = setup_world(db)
    timeline = CampaignCycleStore.timeline(cycle)
    cutoff = timeline.battle_at - timedelta(hours=6)
    economy = CycleEconomyStore()
    state = economy.ensure_state(db, season_id=cycle.season_id, clan_id=clan.id)
    scouts = CycleReconnaissanceService()
    request = scouts.request(db, cycle_id=cycle.id, clan_id=clan.id, territory_id=land.id,
                             scout_user_id=users[2].id, actor_user_id=users[1].id, expected_revision=state.revision, now=timeline.preparation_at)
    assert economy.balance(state).gold == 800
    again = scouts.request(db, cycle_id=cycle.id, clan_id=clan.id, territory_id=land.id,
                           scout_user_id=users[2].id, actor_user_id=users[1].id, expected_revision=1, now=timeline.preparation_at)
    assert again.id == request.id
    assert economy.balance(state).gold == 800
    with pytest.raises(ValueError):
        scouts.request(db, cycle_id=cycle.id, clan_id=clan.id, territory_id=999,
                       scout_user_id=users[2].id, actor_user_id=users[1].id, expected_revision=state.revision, now=timeline.preparation_at)
    other = Clan(name='Secret identity')
    db.add(other)
    db.flush()
    plan = CampaignCyclePlan(cycle_id=cycle.id, clan_id=other.id, revision=2, orders=[])
    db.add(plan)
    db.flush()
    db.add_all([
        CampaignCyclePlanRevision(plan_id=plan.id, revision=1, saved_at=cutoff - timedelta(seconds=1),
            actor_user_id=users[3].id, orders=[{'user_id': 111, 'kind': 'attack', 'territory_id': land.id},
                                             {'user_id': 222, 'kind': 'ambush', 'territory_id': land.id}]),
        CampaignCyclePlanRevision(plan_id=plan.id, revision=2, saved_at=cutoff + timedelta(seconds=1),
            actor_user_id=users[3].id, orders=[]),
    ])
    db.flush()
    assert scouts.report(db, request_id=request.id, actor_user_id=users[2].id, now=cutoff - timedelta(seconds=1)) is None
    report = scouts.report(db, request_id=request.id, actor_user_id=users[2].id, now=timeline.battle_at)
    assert report == {'enemy_squads': [1]}
    assert 'Secret identity' not in str(report)
    with pytest.raises(PermissionError):
        scouts.report(db, request_id=request.id, actor_user_id=users[3].id, now=timeline.battle_at)


def test_scout_cannot_be_ordered_at_or_after_six_hour_cutoff(db):
    users, clan, land, cycle = setup_world(db)
    state = CycleEconomyStore().ensure_state(db, season_id=cycle.season_id, clan_id=clan.id)
    with pytest.raises(ValueError):
        CycleReconnaissanceService().request(db, cycle_id=cycle.id, clan_id=clan.id, territory_id=land.id,
            actor_user_id=users[0].id, expected_revision=state.revision,
            now=CampaignCycleStore.timeline(cycle).battle_at - timedelta(hours=6))
