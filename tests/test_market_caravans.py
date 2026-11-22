from datetime import timedelta

import pytest

from app.core.exceptions import InsufficientPermissionsException
from app.core.time import utc_now
from app.models.clan import Clan, ClanMember
from app.models.market import MarketOffer, TradeCaravan
from app.models.territory import Territory
from app.models.user import User
from app.services.market_service import ClanMarketService


def make_clan(db, name, leader, **resources):
    clan = Clan(
        name=name,
        leader_id=leader.id,
        base_influence=100,
        territory_points=100,
        gold=resources.get("gold", 100),
        resources=resources.get("gold", 100),
        iron=resources.get("iron", 20),
        wood=resources.get("wood", 20),
        food=resources.get("food", 20),
        mithril=resources.get("mithril", 20),
    )
    db.add(clan)
    db.flush()
    db.add(
        ClanMember(
            user_id=leader.id,
            clan_id=clan.id,
            rank="Глава клана",
        )
    )
    return clan


def test_market_reserves_two_cargoes_and_delivers_once(db):
    creator_user = User(username="market_creator", email="creator@test", hashed_password="x")
    accepter_user = User(username="market_accepter", email="accepter@test", hashed_password="x")
    db.add_all([creator_user, accepter_user])
    db.flush()
    creator = make_clan(db, "Купцы Запада", creator_user)
    accepter = make_clan(db, "Кузни Востока", accepter_user)
    first = Territory(
        name="Западный тракт",
        region="eriador",
        svg_path_data="M 0 0 L 2 0 L 1 1 Z",
        owner_clan_id=creator.id,
        adjacent_territory_ids=[],
    )
    second = Territory(
        name="Восточный тракт",
        region="rhun",
        svg_path_data="M 2 0 L 4 0 L 3 1 Z",
        owner_clan_id=accepter.id,
        adjacent_territory_ids=[],
    )
    db.add_all([first, second])
    db.flush()
    first.adjacent_territory_ids = [second.id]
    second.adjacent_territory_ids = [first.id]
    db.commit()

    service = ClanMarketService()
    offer = service.create_offer(
        db,
        creator_clan_id=creator.id,
        give_resource="wood",
        give_amount=5,
        receive_resource="iron",
        receive_amount=4,
        expires_in_days=7,
        current_user=creator_user,
    )
    accepted = service.accept_offer(
        db,
        offer_id=offer["id"],
        accepter_clan_id=accepter.id,
        current_user=accepter_user,
    )

    assert accepted["status"] == "in_transit"
    assert accepted["route_steps"] == 1
    assert accepted["creator_shipping_cost"] == 12
    assert accepted["accepter_shipping_cost"] == 12
    assert creator.wood == 15
    assert accepter.iron == 16
    assert creator.gold == 88
    assert accepter.gold == 88
    assert db.query(TradeCaravan).filter(TradeCaravan.offer_id == offer["id"]).count() == 2

    stored = db.get(MarketOffer, offer["id"])
    stored.eta = utc_now() - timedelta(seconds=1)
    for caravan in stored.caravans:
        caravan.eta = stored.eta
    db.commit()

    assert service.settle_due(db) == 1
    assert creator.iron == 24
    assert accepter.wood == 25
    assert service.settle_due(db) == 0
    assert creator.iron == 24
    assert accepter.wood == 25


def test_market_requires_both_clans_on_map(db):
    first_user = User(username="landed", email="landed@test", hashed_password="x")
    second_user = User(username="landless", email="landless@test", hashed_password="x")
    db.add_all([first_user, second_user])
    db.flush()
    first = make_clan(db, "Землевладельцы", first_user)
    second = make_clan(db, "Безземельные", second_user)
    db.add(
        Territory(
            name="Единственная земля",
            region="gondor",
            svg_path_data="M 0 0 L 1 0 L 1 1 Z",
            owner_clan_id=first.id,
        )
    )
    db.commit()

    service = ClanMarketService()
    offer = service.create_offer(
        db,
        creator_clan_id=first.id,
        give_resource="wood",
        give_amount=1,
        receive_resource="iron",
        receive_amount=1,
        expires_in_days=7,
        current_user=first_user,
    )
    quote = service.quote_for_clan(db, db.get(MarketOffer, offer["id"]), second.id)
    assert quote == {
        "available": False,
        "reason_code": "accepter_has_no_territory",
        "reason": "У вашего клана нет территории на карте",
    }
    with pytest.raises(InsufficientPermissionsException):
        service.accept_offer(
            db,
            offer_id=offer["id"],
            accepter_clan_id=second.id,
            current_user=second_user,
        )


def test_market_uses_sea_route_when_both_clans_own_ports(db):
    first_user = User(username="sea_creator", email="sea-creator@test", hashed_password="x")
    second_user = User(username="sea_accepter", email="sea-accepter@test", hashed_password="x")
    db.add_all([first_user, second_user])
    db.flush()
    first = make_clan(db, "Гавань Запада", first_user)
    second = make_clan(db, "Гавань Юга", second_user)
    db.add_all(
        [
            Territory(
                name="Западный порт",
                region="eriador",
                svg_path_data="M 0 0 L 2 0 L 1 1 Z",
                owner_clan_id=first.id,
                has_port=True,
                adjacent_territory_ids=[],
            ),
            Territory(
                name="Южный порт",
                region="harad",
                svg_path_data="M 20 0 L 22 0 L 21 1 Z",
                owner_clan_id=second.id,
                has_port=True,
                adjacent_territory_ids=[],
            ),
        ]
    )
    db.commit()

    service = ClanMarketService()
    offer = service.create_offer(
        db,
        creator_clan_id=first.id,
        give_resource="wood",
        give_amount=5,
        receive_resource="iron",
        receive_amount=4,
        expires_in_days=7,
        current_user=first_user,
    )
    quote = service.quote_for_clan(db, db.get(MarketOffer, offer["id"]), second.id)
    accepted = service.accept_offer(
        db,
        offer_id=offer["id"],
        accepter_clan_id=second.id,
        current_user=second_user,
    )

    assert quote["available"] is True
    assert quote["route_mode"] == "sea"
    assert quote["route_steps"] == 2
    assert quote["travel_hours"] == 16
    assert quote["route"][1]["via"] == "sea"
    assert accepted["route_mode"] == "sea"
    assert accepted["route_steps"] == 2
    caravans = (
        db.query(TradeCaravan)
        .filter(TradeCaravan.offer_id == offer["id"])
        .order_by(TradeCaravan.id.asc())
        .all()
    )
    assert len(caravans) == 2
    assert service.serialize_caravan(caravans[0])["route_mode"] == "sea"
    assert service.serialize_caravan(caravans[1])["route_mode"] == "sea"
