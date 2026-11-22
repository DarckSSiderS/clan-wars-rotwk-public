from datetime import timedelta

import pytest

from app.models.campaign import CampaignSeason, CampaignRuleSet
from app.core.campaign_rules import default_campaign_rule_values
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.cycle_startup import CycleStartup
from app.models.cycle_market import CycleMarketCaravan
from app.core.time import as_utc
from tests.test_cycle_market_service import market, create, accept
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_runtime_service import CycleRuntimeService
from app.services.cycle_startup_service import CycleStartupService
from tests.test_campaign_cycle_store import START, season
from tests.test_cycle_reveal_service import prepared


def test_legacy_season_is_not_touched(db):
    row = season(db, enabled=False)
    assert CycleRuntimeService().tick(db, now=START) is False
    assert db.query(CampaignCycleRecord).count() == 0
    assert db.get(CampaignSeason, row.id).status == 'active'


def test_worker_never_guesses_initial_ownership_or_starts_season(db):
    row = season(db)
    with pytest.raises(ValueError, match='explicit'):
        CycleRuntimeService().tick(db, now=START)
    assert db.query(CycleStartup).count() == 0
    assert db.query(CampaignCycleRecord).count() == 0
    cycle = CampaignCycleStore().start(db, season_id=row.id)
    with pytest.raises(ValueError, match='startup'):
        CycleRuntimeService().tick(db, now=START)
    assert cycle.orders_frozen_at is None


def test_runtime_reveals_orders_but_does_not_certify_arena_coverage(db):
    _, _, _, _, cycle, now = prepared(db)
    # The initializer is explicit and trusted, not done by tick after an outage.
    startup = CycleStartupService().initialize(db, cycle_id=cycle.id, now=START)
    startup.expired_at = CampaignCycleStore.timeline(cycle).preparation_at
    db.flush()
    service = CycleRuntimeService()
    assert service.tick(db, now=now) is True
    assert cycle.orders_frozen_at is not None
    assert cycle.import_verified_at is None
    service.tick(db, now=CampaignCycleStore.timeline(cycle).replay_deadline)
    assert cycle.settled_at is None


def test_runtime_checks_ready_interceptions_without_certifying_import(db, monkeypatch):
    from app.services.cycle_interception_service import CycleInterceptionService
    _, _, _, _, cycle, now = prepared(db)
    startup = CycleStartupService().initialize(db, cycle_id=cycle.id, now=START)
    startup.expired_at = CampaignCycleStore.timeline(cycle).preparation_at
    db.flush()
    checked = []
    monkeypatch.setattr(CycleInterceptionService, 'settle_ready',
        lambda self, db, **kwargs: checked.append(kwargs))
    CycleRuntimeService().tick(db, now=now)
    assert checked == [{'cycle_id': cycle.id, 'now': now}]
    assert cycle.import_verified_at is None


def test_missed_preparation_does_not_invent_historical_plan_snapshot(db):
    row = season(db)
    cycle = CampaignCycleStore().start(db, season_id=row.id)
    CycleStartupService().initialize(db, cycle_id=cycle.id, now=START)
    with pytest.raises(ValueError, match='preparation'):
        CycleRuntimeService().tick(db, now=CampaignCycleStore.timeline(cycle).battle_at)
    db.refresh(cycle)
    assert cycle.planning_snapshot is None and cycle.orders_frozen_at is None


def test_registration_expiry_precedes_preparation_snapshot(db):
    row = season(db)
    cycle = CampaignCycleStore().start(db, season_id=row.id)
    startup = CycleStartupService().initialize(db, cycle_id=cycle.id, now=START)
    CycleRuntimeService().tick(db, now=START + timedelta(hours=72))
    assert startup.expired_at is not None
    assert cycle.planning_snapshot == []


def test_verified_cycle_settles_and_long_outage_does_not_shorten_preparation(db):
    _, _, _, _, cycle, now = prepared(db)
    startup = CycleStartupService().initialize(db, cycle_id=cycle.id, now=START)
    startup.expired_at = CampaignCycleStore.timeline(cycle).preparation_at
    db.add(CampaignRuleSet(version=cycle.rule_version, values=default_campaign_rule_values(),
                           is_active=True, reason='Frozen test rules'))
    db.flush()
    service = CycleRuntimeService()
    service.tick(db, now=now)
    completed_at = CampaignCycleStore.timeline(cycle).replay_deadline
    CampaignCycleStore().mark_import_complete(db, cycle_id=cycle.id, verified_at=completed_at)
    service.tick(db, now=completed_at)
    assert cycle.settled_at is not None
    restarted_at = completed_at + timedelta(days=3)
    service.tick(db, now=restarted_at)
    following = db.query(CampaignCycleRecord).filter_by(season_id=cycle.season_id, number=2).one()
    assert CampaignCycleStore.timeline(following).preparation_at == restarted_at
    assert following.planning_snapshot is not None
    assert following.orders_frozen_at is None


def test_finished_season_delivers_accepted_cargo_without_falling_back_to_legacy(db, market):
    _, _, _, wallets, _, _, row = market
    offer = create(db, market)
    accept(db, market, offer)
    row.status = 'completed'
    db.flush()
    cars = db.query(CycleMarketCaravan).all()
    at = max(as_utc(car.arrives_at) for car in cars)
    service = CycleRuntimeService()
    assert service.tick(db, now=at) is True
    assert all(car.delivered_at is not None for car in cars)
    balances = [dict(wallet.wallet) for wallet in wallets]
    assert service.tick(db, now=at + timedelta(days=1)) is True
    assert [wallet.wallet for wallet in wallets] == balances
