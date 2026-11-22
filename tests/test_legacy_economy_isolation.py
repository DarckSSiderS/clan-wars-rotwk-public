from datetime import timedelta

import pytest

from app.core.exceptions import InsufficientPermissionsException
from app.core.time import utc_now
from app.models.campaign import CampaignSeason
from app.models.clan_asset import ClanAsset
from app.models.market import MarketOffer
from app.models.operation import ResourceLedgerEntry
from app.models.territory import Territory
from app.models.user import User
from app.services.clan_economy_service import ClanEconomyService
from app.services.market_service import ClanMarketService
from tests.test_market_caravans import make_clan


@pytest.fixture
def legacy_world(db):
    users = [User(username=f'isolation-{i}', email=f'isolation-{i}@test',
                  hashed_password='x') for i in range(2)]
    db.add_all(users)
    db.flush()
    clans = [make_clan(db, f'Isolation {i}', user, gold=10000)
             for i, user in enumerate(users)]
    territories = [Territory(name=f'Isolation land {i}', region='gondor',
                             svg_path_data='M 0 0 L 1 0 L 1 1 Z',
                             owner_clan_id=clan.id, population=10000)
                   for i, clan in enumerate(clans)]
    asset = ClanAsset(key='isolation_relic', name='Isolation relic',
                      bonus_type='attack_power', bonus_value=1, gold_cost=10,
                      required_influence_level_1=0)
    db.add_all([*territories, asset])
    db.flush()
    territories[0].adjacent_territory_ids = [territories[1].id]
    territories[1].adjacent_territory_ids = [territories[0].id]
    db.commit()
    return users, clans, territories, asset


def add_season(db, *, number=1, status='active', cycle=True):
    row = CampaignSeason(number=number, name=f'Isolation season {number}',
                         status=status, starts_at=utc_now(),
                         rules_snapshot={'mechanics_version': 'cycle_v1'} if cycle else {})
    db.add(row)
    db.commit()
    return row


def create_offer(db, world):
    users, clans, _, _ = world
    result = ClanMarketService().create_offer(
        db, creator_clan_id=clans[0].id, give_resource='wood', give_amount=5,
        receive_resource='iron', receive_amount=4, expires_in_days=7,
        current_user=users[0])
    return db.get(MarketOffer, result['id'])


@pytest.mark.parametrize('status', ['active', 'finished'])
@pytest.mark.parametrize('mutation', ['purchase', 'loadout', 'upgrade', 'create', 'accept', 'cancel'])
def test_cycle_campaign_rejects_legacy_mutations(db, legacy_world, status, mutation):
    users, clans, territories, asset = legacy_world
    season = add_season(db, cycle=False)
    offer = create_offer(db, legacy_world)
    season.rules_snapshot = {'mechanics_version': 'cycle_v1'}
    season.status = status
    db.commit()
    economy, market = ClanEconomyService(), ClanMarketService()
    before = (clans[0].gold, clans[0].wood, clans[1].iron,
              territories[0].population, db.query(ResourceLedgerEntry).count())
    commands = {
        'purchase': lambda: economy.purchase_asset(db, clans[0].id, asset.id, users[0]),
        'loadout': lambda: economy.update_relic_loadout(db, clans[0].id, [], users[0]),
        'upgrade': lambda: economy.upgrade_territory(db, territories[0].id, 'population', 1, users[0]),
        'create': lambda: create_offer(db, legacy_world),
        'accept': lambda: market.accept_offer(db, offer_id=offer.id,
                                             accepter_clan_id=clans[1].id, current_user=users[1]),
        'cancel': lambda: market.cancel_offer(db, offer_id=offer.id, current_user=users[0]),
    }
    with pytest.raises(InsufficientPermissionsException, match='cycle'):
        commands[mutation]()
    assert before == (clans[0].gold, clans[0].wood, clans[1].iron,
                      territories[0].population, db.query(ResourceLedgerEntry).count())
    assert offer.status == 'open'
    assert db.query(MarketOffer).count() == 1


@pytest.mark.parametrize('status', ['active', 'finished'])
def test_cycle_settlement_is_noop_and_legacy_reads_stay_usable(db, legacy_world, status):
    _, clans, _, _ = legacy_world
    offer = create_offer(db, legacy_world)
    add_season(db, status=status)
    clan = clans[0]
    clan.last_economy_tick = utc_now() - timedelta(days=3)
    db.commit()
    before = {column.name: getattr(clan, column.name) for column in clan.__table__.columns}
    ledger_count = db.query(ResourceLedgerEntry).count()
    economy = ClanEconomyService()
    assert economy.settle_clan(db, clan) is clan
    assert before == {column.name: getattr(clan, column.name) for column in clan.__table__.columns}
    assert economy.get_clan_economy(db, clan.id)['gold'] == before['gold']
    assert isinstance(economy.list_assets(db, clan.id), list)
    listing = ClanMarketService().list_market(db, clans[1].id)
    quote = listing['offers'][0]['quote']
    assert quote['available'] is False
    assert quote['reason_code'] == 'cycle_campaign'
    assert ClanMarketService().quote_for_clan(db, offer, clans[1].id) == quote
    db.refresh(clan)
    assert before == {column.name: getattr(clan, column.name) for column in clan.__table__.columns}
    assert db.query(ResourceLedgerEntry).count() == ledger_count


@pytest.mark.parametrize('active_cycle,latest_cycle,blocked', [
    (True, False, True), (False, True, False), (None, True, True),
    (None, False, False),
])
def test_active_season_takes_precedence_otherwise_latest_owns_campaign(
        db, legacy_world, active_cycle, latest_cycle, blocked):
    users, clans, _, asset = legacy_world
    if active_cycle is not None:
        add_season(db, cycle=active_cycle)
    add_season(db, number=2, status='finished', cycle=latest_cycle)
    if blocked:
        with pytest.raises(InsufficientPermissionsException, match='cycle'):
            ClanEconomyService().purchase_asset(db, clans[0].id, asset.id, users[0])
    else:
        owned = ClanEconomyService().purchase_asset(db, clans[0].id, asset.id, users[0])
        assert owned.level == 1
        assert clans[0].gold == 9990


def test_accepted_legacy_caravans_still_arrive_in_cycle_mode(db, legacy_world):
    users, clans, _, _ = legacy_world
    season = add_season(db, cycle=False)
    offer = create_offer(db, legacy_world)
    service = ClanMarketService()
    service.accept_offer(db, offer_id=offer.id, accepter_clan_id=clans[1].id,
                         current_user=users[1])
    season.rules_snapshot = {'mechanics_version': 'cycle_v1'}
    offer.eta = utc_now() - timedelta(seconds=1)
    for caravan in offer.caravans:
        caravan.eta = offer.eta
    db.commit()
    assert service.settle_due(db) == 1
    assert offer.status == 'completed'
    assert clans[0].iron == 24
    assert clans[1].wood == 25
    assert all(caravan.status == 'delivered' for caravan in offer.caravans)
    assert service.settle_due(db) == 0


@pytest.mark.parametrize('status', ['active', 'finished'])
def test_legacy_get_endpoints_remain_available_in_cycle_mode(db, legacy_world, status):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1.clans import router
    from app.core.auth import get_current_active_user
    from app.database import get_db

    users, clans, _, _ = legacy_world
    create_offer(db, legacy_world)
    add_season(db, status=status)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: users[1]
    client = TestClient(app)
    for path in (f'/clans/{clans[0].id}/economy', f'/clans/{clans[0].id}/assets',
                 f'/clans/market/offers?clan_id={clans[1].id}'):
        response = client.get(path)
        assert response.status_code == 200, response.text
