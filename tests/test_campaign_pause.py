import asyncio
from contextlib import nullcontext
from datetime import timedelta

import pytest
from fastapi import HTTPException

import app.services.scheduler_service as scheduler_module
from app.api.v1.campaign_guard import require_campaign_running
from app.core.time import as_utc, utc_now
from app.models.campaign import CampaignRuleSet, CampaignSettings
from app.models.clan import Clan
from app.models.clan_warfare import ClanAttackPointSpend
from app.models.market import MarketOffer, TradeCaravan
from app.models.operation import AdminAuditLog
from app.models.territory import Territory
from app.models.user import User
from app.models.war import ClanWar
from app.services.campaign_pause_service import CampaignPauseService
from app.services.scheduler_service import CampaignWorker


def test_campaign_pause_resume_shifts_active_deadlines_once(db):
    paused_at = utc_now()
    resumed_at = paused_at + timedelta(hours=3)
    admin = User(
        username="pause-admin",
        email="pause-admin@example.test",
        hashed_password="unused",
        is_claimed=True,
        is_active=True,
    )
    clan = Clan(
        name="Хранители времени",
        leader=admin,
        last_economy_tick=paused_at - timedelta(hours=1),
        next_attack_at=paused_at + timedelta(hours=5),
    )
    rule_set = CampaignRuleSet(
        version=1,
        values={},
        is_active=True,
        reason="test",
    )
    territory = Territory(
        name="Земля времени",
        region="test",
        svg_path_data="M 0 0",
        owner_clan=clan,
        owned_since=paused_at - timedelta(days=2),
        last_weekly_payout_at=paused_at - timedelta(days=1),
    )
    db.add_all([admin, clan, rule_set, territory])
    db.flush()
    war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=clan.id,
        war_type="neutral_capture",
        status="active",
        ends_at=paused_at + timedelta(hours=8),
    )
    spend = ClanAttackPointSpend(
        clan_id=clan.id,
        war=war,
        origin="war_started",
        spent_at=paused_at - timedelta(hours=1),
        recover_at=paused_at + timedelta(hours=5),
        level_snapshot=1,
        capacity_snapshot=1,
        campaign_rule_set_id=rule_set.id,
        rule_version=1,
    )
    offer = MarketOffer(
        creator_clan_id=clan.id,
        created_by_user_id=admin.id,
        give_resource="wood",
        give_amount=1,
        receive_resource="iron",
        receive_amount=1,
        status="in_transit",
        expires_at=paused_at + timedelta(hours=4),
        eta=paused_at + timedelta(hours=7),
    )
    open_offer = MarketOffer(
        creator_clan_id=clan.id,
        created_by_user_id=admin.id,
        give_resource="food",
        give_amount=1,
        receive_resource="wood",
        receive_amount=1,
        status="open",
        expires_at=paused_at + timedelta(hours=4),
    )
    caravan = TradeCaravan(
        offer=offer,
        from_clan_id=clan.id,
        to_clan_id=clan.id,
        resource="wood",
        amount=1,
        status="traveling",
        route=[],
        departed_at=paused_at - timedelta(hours=1),
        eta=paused_at + timedelta(hours=7),
    )
    db.add_all([war, spend, offer, open_offer, caravan])
    db.commit()

    service = CampaignPauseService()
    paused = service.pause(
        db,
        actor_user_id=admin.id,
        reason="Технические работы",
        now=paused_at,
    )
    repeated_pause = service.pause(
        db,
        actor_user_id=admin.id,
        reason="Повтор команды",
        now=paused_at + timedelta(hours=1),
    )
    assert paused.is_paused is True
    assert as_utc(repeated_pause.paused_at) == paused_at
    with pytest.raises(HTTPException) as paused_error:
        require_campaign_running(db)
    assert paused_error.value.status_code == 409

    resumed = service.resume(
        db,
        actor_user_id=admin.id,
        reason="Работы завершены",
        now=resumed_at,
    )
    service.resume(
        db,
        actor_user_id=admin.id,
        reason="Повтор команды",
        now=resumed_at + timedelta(hours=1),
    )

    db.refresh(war)
    db.refresh(spend)
    db.refresh(clan)
    db.refresh(territory)
    db.refresh(offer)
    db.refresh(open_offer)
    db.refresh(caravan)
    assert resumed.is_paused is False
    require_campaign_running(db)
    assert as_utc(war.ends_at) == paused_at + timedelta(hours=11)
    assert as_utc(spend.recover_at) == paused_at + timedelta(hours=8)
    assert as_utc(clan.next_attack_at) == paused_at + timedelta(hours=8)
    assert as_utc(clan.last_economy_tick) == paused_at + timedelta(hours=2)
    assert as_utc(territory.last_weekly_payout_at) == paused_at - timedelta(hours=21)
    assert as_utc(open_offer.expires_at) == paused_at + timedelta(hours=7)
    assert as_utc(offer.eta) == paused_at + timedelta(hours=10)
    assert as_utc(caravan.eta) == paused_at + timedelta(hours=10)
    assert [row.action for row in db.query(AdminAuditLog).order_by(AdminAuditLog.id)] == [
        "campaign_paused",
        "campaign_resumed",
    ]


def test_paused_worker_keeps_sync_but_skips_campaign_timers(db, monkeypatch):
    db.add(CampaignSettings(id=1, is_paused=True, paused_at=utc_now()))
    db.commit()
    events = []
    worker = CampaignWorker(interval_seconds=600)

    async def complete_due_wars():
        events.append("wars")
        return 0

    class FakeLadderService:
        async def fetch_and_save_matches(self, _db, limit):
            events.append("ladder")
            return 0

    class FakeBackfillService:
        async def process_pending(self, _db):
            events.append("backfill")
            return 0

    class FakeEconomyService:
        def settle_all(self, _db):
            events.append("economy")

    class FakeMarketService:
        def settle_due(self, _db):
            events.append("market")

        def expire_open_offers(self, _db):
            events.append("expiry")

    worker._complete_due_wars = complete_due_wars
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr(scheduler_module, "BFMELadderService", FakeLadderService)
    monkeypatch.setattr(
        scheduler_module,
        "ArenaMatchBackfillService",
        FakeBackfillService,
    )
    monkeypatch.setattr(scheduler_module, "ClanEconomyService", FakeEconomyService)
    monkeypatch.setattr(scheduler_module, "ClanMarketService", FakeMarketService)

    asyncio.run(worker.run_cycle())

    assert events == ["ladder", "backfill"]
    assert worker._next_war_end(db) is None
