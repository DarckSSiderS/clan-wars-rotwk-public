from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.core.exceptions import InsufficientPermissionsException
from app.core.time import utc_now
from app.models.clan import Clan
from app.models.market import MarketOffer, TradeCaravan
from app.models.match import Match
from app.models.operation import ResourceLedgerEntry
from app.models.territory import Territory
from app.models.user import User
from app.models.worker import WorkerHeartbeat
from app.services.clan_service import ClanService
from app.services.clan_economy_service import ClanEconomyService
from app.services.market_service import ClanMarketService
from app.services.operation_service import ResourceLedgerService
from app.services.war_service import ClanWarService
from test_market_caravans import make_clan
from test_war_deployment_scoring import _active_v3_war, _match


def in_transit_trade(db):
    users = [User(username=f"trader-{i}", email=f"trader-{i}@example.test", hashed_password="x") for i in range(2)]
    db.add_all(users)
    db.flush()
    clans = [make_clan(db, f"Trading clan {i}", user) for i, user in enumerate(users)]
    territories = [Territory(name=f"Trade road {i}", region="eriador", svg_path_data="M0 0", owner_clan_id=clan.id) for i, clan in enumerate(clans)]
    db.add_all(territories)
    db.flush()
    territories[0].adjacent_territory_ids = [territories[1].id]
    territories[1].adjacent_territory_ids = [territories[0].id]
    db.commit()
    service = ClanMarketService()
    offer = service.create_offer(db, creator_clan_id=clans[0].id, give_resource="wood", give_amount=5, receive_resource="iron", receive_amount=4, expires_in_days=7, current_user=users[0])
    service.accept_offer(db, offer_id=offer["id"], accepter_clan_id=clans[1].id, current_user=users[1])
    assert clans[0].wood == 15 and clans[1].iron == 16
    return clans, db.get(MarketOffer, offer["id"])


def test_deleted_trade_partner_refunds_cargo_once_and_keeps_history(postgres_db):
    db = postgres_db
    clans, offer = in_transit_trade(db)
    creator_id, survivor_id, offer_id = clans[0].id, clans[1].id, offer.id
    assert ClanService().delete_clan(db, creator_id)
    assert ClanService().delete_clan(db, creator_id)
    assert ClanMarketService().settle_due(db) == 0
    assert db.get(Clan, survivor_id).iron == 20
    assert db.get(MarketOffer, offer_id).status == "failed"
    assert db.query(TradeCaravan).filter_by(status="failed").count() == 2
    assert db.query(ResourceLedgerEntry).filter_by(clan_id=survivor_id, action="market_cargo_refunded").count() == 1


def test_season_reset_cancels_previous_cargo_and_open_offers(postgres_db):
    db = postgres_db
    clans, offer = in_transit_trade(db)
    service = ClanMarketService()
    extra = service.create_offer(db, creator_clan_id=clans[0].id, give_resource="wood", give_amount=1, receive_resource="iron", receive_amount=1, expires_in_days=7, current_user=db.get(User, clans[0].leader_id))
    ClanEconomyService().start_new_season(db, starting_influence=100)
    before = {clan.id: (clan.wood, clan.iron, clan.gold, clan.resources) for clan in clans}
    offer.eta = utc_now() - timedelta(seconds=1)
    db.commit()
    assert service.settle_due(db) == 0
    assert {clan.id: (clan.wood, clan.iron, clan.gold, clan.resources) for clan in clans} == before
    assert db.get(MarketOffer, extra["id"]).status == "canceled"
    assert offer.status == "failed"


@pytest.mark.parametrize("same_territory,starting_gold", [(False, 1000), (True, 1000), (False, 100)])
def test_parallel_upgrades_have_consistent_balances_and_levels(postgres_db, same_territory, starting_gold):
    db = postgres_db
    user = User(username="builder", email="builder@example.test", hashed_password="x")
    db.add(user)
    db.flush()
    clan = make_clan(db, "Builders", user, gold=starting_gold, iron=1000, wood=1000, food=1000)
    clan.last_economy_tick = utc_now()
    territories = [Territory(name=f"Review land {i}", region="gondor", svg_path_data="M0 0", owner_clan_id=clan.id, owned_since=utc_now(), resource_income_ready_at=utc_now()+timedelta(days=2)) for i in range(2)]
    db.add_all(territories)
    db.flush()
    ClanEconomyService().settle_clan(db, clan)
    db.commit()
    user_id, clan_id = user.id, clan.id
    territory_ids = [territory.id for territory in territories]
    sessions = sessionmaker(bind=db.get_bind(), autoflush=False)
    barrier = Barrier(2, timeout=10)

    def buy(territory_id):
        with sessions() as session:
            # Keep stale ORM reads alive: SELECT FOR UPDATE must refresh them.
            loaded_clan = session.get(Clan, clan_id)
            loaded_territory = session.get(Territory, territory_id)
            operator = session.get(User, user_id)
            assert loaded_clan.gold == starting_gold and loaded_territory.fortifications == 0
            barrier.wait()
            try:
                return ClanEconomyService().upgrade_territory(session, territory_id, "fortifications", 1, operator)["cost"]
            except InsufficientPermissionsException:
                session.rollback()
                return None

    targets = [territory_ids[0]] * 2 if same_territory else territory_ids
    with ThreadPoolExecutor(max_workers=2) as executor:
        costs = [cost for cost in executor.map(buy, targets) if cost is not None]
    db.expire_all()
    entries = db.query(ResourceLedgerEntry).filter_by(clan_id=clan_id, resource="gold", action="territory_upgrade").all()
    assert len(costs) == (1 if starting_gold == 100 else 2)
    assert len(entries) == len(costs)
    assert db.get(Clan, clan_id).gold == starting_gold - sum(cost["gold"] for cost in costs)
    assert sum(db.get(Territory, territory_id).fortifications for territory_id in territory_ids) == len(costs)


def test_parallel_repeated_ledger_key_is_applied_once(postgres_db):
    db = postgres_db
    clans, _ = in_transit_trade(db)
    clan_id, starting_gold = clans[0].id, clans[0].gold
    sessions = sessionmaker(bind=db.get_bind(), autoflush=False)
    barrier = Barrier(2, timeout=10)

    def credit(_):
        with sessions() as session:
            clan = session.get(Clan, clan_id)
            barrier.wait()
            _, applied = ResourceLedgerService().apply_change(session, clan, resource="gold", amount=10, operation_id="same-credit", action="test")
            session.commit()
            return applied

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(credit, range(2))) == [False, True]
    db.expire_all()
    assert db.get(Clan, clan_id).gold == starting_gold + 10


def test_parallel_caravan_delivery_is_applied_once(postgres_db):
    db = postgres_db
    clans, offer = in_transit_trade(db)
    clan_ids = [clan.id for clan in clans]
    offer.eta = utc_now() - timedelta(seconds=1)
    db.commit()
    sessions = sessionmaker(bind=db.get_bind(), autoflush=False)
    barrier = Barrier(2, timeout=10)

    def deliver(_):
        with sessions() as session:
            barrier.wait()
            return ClanMarketService().settle_due(session)

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(deliver, range(2))) == [0, 1]
    db.expire_all()
    assert db.get(Clan, clan_ids[0]).iron == 24
    assert db.get(Clan, clan_ids[1]).wood == 25


def test_war_waits_for_grace_and_complete_sync_and_counts_entire_batch(postgres_db, monkeypatch):
    db = postgres_db
    war, _, attackers, _, defenders = _active_v3_war(db)
    with patch.object(ClanWarService, "record_match_result", return_value=None):
        for suffix in ("late-a", "late-b"):
            try:
                _match(db, war, attackers[:1], defenders[:1], suffix)
            except IndexError:
                pass  # Fixture expects scoring, intentionally deferred until sync.
    matches = db.query(Match).order_by(Match.id).all()
    for match in matches:
        match.match_date = war.ends_at - timedelta(minutes=5)
    db.commit()
    now = war.ends_at + timedelta(seconds=1)
    monkeypatch.setattr("app.services.war_service.utc_now", lambda: now)
    service = ClanWarService()
    assert service.complete_expired_wars(db) == 0
    for match in matches:
        service.record_match_result(db, attackers[0].username, defenders[0].username, match_date=match.match_date, match=match)
    db.commit()
    db.refresh(war)
    assert len(war.match_results) == 2 and war.status == "active"
    now = war.ends_at + timedelta(minutes=settings.WAR_REPLAY_GRACE_MINUTES, seconds=1)
    assert service.complete_expired_wars(db) == 0  # No successful scan yet.
    heartbeat = WorkerHeartbeat(worker_name="campaign", replay_synced_through_at=war.ends_at)
    db.add(heartbeat)
    db.commit()
    assert service.complete_expired_wars(db) == 0  # A pre-grace scan is insufficient.
    heartbeat.replay_synced_through_at = now
    db.commit()
    assert service.complete_expired_wars(db) == 1
    db.refresh(war)
    assert war.status == "completed" and len(war.match_results) == 2


@pytest.mark.parametrize("transition", ["delete", "season"])
def test_caravan_delivery_cannot_cross_clan_or_season_transition(postgres_db, transition):
    db = postgres_db
    clans, offer = in_transit_trade(db)
    creator_id, survivor_id, offer_id = clans[0].id, clans[1].id, offer.id
    offer.eta = utc_now() - timedelta(seconds=1)
    db.commit()
    sessions = sessionmaker(bind=db.get_bind(), autoflush=False)
    barrier = Barrier(2, timeout=10)

    def mutate(kind):
        with sessions() as session:
            barrier.wait()
            if kind == "deliver":
                return ClanMarketService().settle_due(session)
            if transition == "delete":
                return ClanService().delete_clan(session, creator_id)
            return ClanEconomyService().start_new_season(session, starting_influence=100)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(mutate, ["deliver", "transition"]))
    db.expire_all()
    survivor = db.get(Clan, survivor_id)
    if transition == "season":
        assert (survivor.wood, survivor.iron) == (6, 6)
    else:
        assert (survivor.wood, survivor.iron) in {(25, 16), (20, 20)}
    assert db.get(MarketOffer, offer_id).status in {"completed", "failed"}
    assert db.query(TradeCaravan).count() == 2
