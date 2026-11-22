from datetime import datetime, timedelta, timezone
from math import ceil

from app.models.clan import Clan, ClanMember
from app.models.market import MarketOffer, TradeCaravan
from app.models.territory import Territory
from app.models.user import User
from app.services.campaign_rule_service import CampaignRuleService
from app.services.market_service import ClanMarketService


def _market_fixture(db):
    creator_user = User(
        username="rule-market-creator",
        email="rule-market-creator@example.com",
        hashed_password="unused",
    )
    accepter_user = User(
        username="rule-market-accepter",
        email="rule-market-accepter@example.com",
        hashed_password="unused",
    )
    db.add_all([creator_user, accepter_user])
    db.flush()
    creator = Clan(
        name="Создатели тарифа",
        leader_id=creator_user.id,
        base_influence=100,
        territory_points=100,
        gold=1_000,
        resources=1_000,
        wood=100,
        iron=100,
        food=100,
        mithril=100,
    )
    accepter = Clan(
        name="Получатели тарифа",
        leader_id=accepter_user.id,
        base_influence=100,
        territory_points=100,
        gold=1_000,
        resources=1_000,
        wood=100,
        iron=100,
        food=100,
        mithril=100,
    )
    db.add_all([creator, accepter])
    db.flush()
    db.add_all(
        [
            ClanMember(
                user_id=creator_user.id,
                clan_id=creator.id,
                rank="Глава клана",
            ),
            ClanMember(
                user_id=accepter_user.id,
                clan_id=accepter.id,
                rank="Глава клана",
            ),
        ]
    )
    first = Territory(
        name="Начало торгового пути",
        region="eriador",
        svg_path_data="M 0 0 L 2 0 L 1 1 Z",
        owner_clan_id=creator.id,
        adjacent_territory_ids=[],
        is_playable=True,
    )
    second = Territory(
        name="Конец торгового пути",
        region="rhun",
        svg_path_data="M 2 0 L 4 0 L 3 1 Z",
        owner_clan_id=accepter.id,
        adjacent_territory_ids=[],
        is_playable=True,
    )
    db.add_all([first, second])
    db.flush()
    first.adjacent_territory_ids = [second.id]
    second.adjacent_territory_ids = [first.id]
    db.commit()
    return creator_user, accepter_user, creator, accepter


def _activate(db, actor, **changes):
    rules = CampaignRuleService()
    active = rules.get_active(db)
    return rules.create_version(
        db,
        expected_version=active.version,
        changes=changes,
        actor_user_id=actor.id,
        reason="Проверка тарифа будущей сделки",
        commit=True,
    )


def test_fast_season_uses_base_shipping_quote(db, monkeypatch):
    creator_user, _, creator, accepter = _market_fixture(db)
    now = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    monkeypatch.setattr("app.services.market_service.utc_now", lambda: now)
    service = ClanMarketService()
    offer_payload = service.create_offer(
        db,
        creator_clan_id=creator.id,
        give_resource="wood",
        give_amount=11,
        receive_resource="iron",
        receive_amount=4,
        expires_in_days=7,
        current_user=creator_user,
    )

    quote = service.quote_for_clan(
        db,
        db.get(MarketOffer, offer_payload["id"]),
        accepter.id,
    )

    assert quote["travel_hours"] == quote["route_steps"] * 6
    old_price = max(10, 7 + quote["route_steps"] * 4 + ceil(11 / 7))
    assert quote["creator_shipping_cost"] == old_price


def test_accept_requotes_under_lock_and_saved_caravan_terms_do_not_change(
    db,
    monkeypatch,
):
    creator_user, accepter_user, creator, accepter = _market_fixture(db)
    now = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    monkeypatch.setattr("app.services.market_service.utc_now", lambda: now)
    service = ClanMarketService()
    offer_payload = service.create_offer(
        db,
        creator_clan_id=creator.id,
        give_resource="wood",
        give_amount=11,
        receive_resource="iron",
        receive_amount=4,
        expires_in_days=7,
        current_user=creator_user,
    )
    offer = db.get(MarketOffer, offer_payload["id"])
    old_quote = service.quote_for_clan(db, offer, accepter.id)
    assert old_quote["creator_shipping_cost"] == 13

    _activate(
        db,
        creator_user,
        CARAVAN_HOURS_PER_STEP=9,
        CARAVAN_BASE_GOLD_FEE=10,
        CARAVAN_DISTANCE_GOLD_FEE=4,
        CARAVAN_VOLUME_STEP=10,
        CARAVAN_VOLUME_GOLD_FEE=2,
    )
    accepted = service.accept_offer(
        db,
        offer_id=offer.id,
        accepter_clan_id=accepter.id,
        current_user=accepter_user,
    )

    assert accepted["creator_shipping_cost"] == 18
    assert accepted["accepter_shipping_cost"] == 16
    saved_eta = now + timedelta(hours=9)
    assert accepted["eta"].replace(tzinfo=timezone.utc) == saved_eta
    _activate(db, creator_user, CARAVAN_HOURS_PER_STEP=24)

    db.expire_all()
    stored = db.get(MarketOffer, offer.id)
    assert stored.creator_shipping_cost == 18
    assert stored.accepter_shipping_cost == 16
    assert stored.eta.replace(tzinfo=timezone.utc) == saved_eta
    assert {
        caravan.eta.replace(tzinfo=timezone.utc)
        for caravan in db.query(TradeCaravan).filter_by(offer_id=offer.id).all()
    } == {saved_eta}
