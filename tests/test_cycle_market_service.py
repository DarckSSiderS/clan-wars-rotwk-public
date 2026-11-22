from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.campaign import CampaignSeason
from app.core.time import as_utc
from app.models.clan import Clan, ClanMember
from app.models.cycle_diplomacy import CycleDiplomacyPair
from app.models.cycle_market import CycleMarketCaravan, CycleMarketOffer
from app.models.territory import Territory
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.campaign_rule_service import CampaignRuleService
from app.services.cycle_economy import InsufficientFunds
from app.services.cycle_economy_store import CycleEconomyStore, EconomyConflict
from app.services.cycle_market_service import CycleMarketService
from app.services.market_service import MarketRoute


@pytest.fixture
def market(db, monkeypatch):
    now = datetime(2026, 10, 15, tzinfo=timezone.utc)
    season = CampaignSeason(number=1, name='Market', status='active', starts_at=now,
                            rules_snapshot={'version': 1, 'mechanics_version': 'cycle_v1'})
    clans = [Clan(name=f'Clan {n}', leader_id=10 + n) for n in range(3)]
    db.add_all([season, *clans])
    db.flush()
    cycle = CampaignCycleStore().start(db, season_id=season.id)
    wallets = [CycleEconomyStore().ensure_state(db, season_id=season.id, clan_id=c.id) for c in clans]
    lands = [Territory(name=f'Land {n}', region='R', svg_path_data='', owner_clan_id=c.id,
                       is_playable=True) for n, c in enumerate(clans)]
    db.add_all(lands)
    CampaignRuleService().get_active(db)
    db.flush()
    service = CycleMarketService()
    monkeypatch.setattr(service, '_route', lambda db, first, second: MarketRoute(
        territories=[lands[next(i for i, c in enumerate(clans) if c.id == first)],
                     lands[next(i for i, c in enumerate(clans) if c.id == second)]],
        modes=['land'], travel_steps=1))
    prep = CampaignCycleStore.timeline(cycle).preparation_at
    return service, cycle, clans, wallets, prep, lands, season


def create(db, market, command='create', target=None):
    service, cycle, clans, wallets, now, _, _ = market
    return service.create(db, cycle_id=cycle.id, clan_id=clans[0].id, actor_id=10,
        offered={'iron': '2.5'}, requested={'wood': '3'}, now=now, command_id=command,
        expected_wallet_revision=wallets[0].revision, target_clan_id=target)


def accept(db, market, offer, command='accept', recipient=1):
    service, cycle, clans, wallets, now, _, _ = market
    return service.accept(db, cycle_id=cycle.id, offer_id=offer.id, clan_id=clans[recipient].id,
        actor_id=10 + recipient, now=now, command_id=command, expected_revision=offer.revision,
        expected_sender_revision=wallets[0].revision, expected_wallet_revision=wallets[recipient].revision)


def test_reservation_atomic_fees_transit_and_retries(db, market):
    service, cycle, clans, wallets, now, _, _ = market
    offer = create(db, market)
    assert Decimal(wallets[0].wallet['iron']) == Decimal('27.5')
    assert create(db, market).id == offer.id
    accept(db, market, offer)
    assert Decimal(wallets[0].wallet['iron']) == Decimal('27.5')
    assert Decimal(wallets[0].wallet['wood']) == 30
    assert Decimal(wallets[0].wallet['gold']) == 988
    assert Decimal(wallets[1].wallet['gold']) == Decimal('988.75')
    assert Decimal(wallets[1].wallet['wood']) == 27
    accept(db, market, offer)
    assert db.query(CycleMarketCaravan).count() == 2
    with pytest.raises(ValueError):
        accept(db, market, offer, command='second-accept')


def test_battle_time_trade_is_allowed_and_skips_the_partial_cycle_for_expiry(db, market):
    service, cycle, clans, wallets, _, lands, season = market
    battle_time = CampaignCycleStore.timeline(cycle).battle_at + timedelta(hours=1)
    during_battle = (service, cycle, clans, wallets, battle_time, lands, season)
    offer = create(db, during_battle)
    assert offer.first_full_cycle == cycle.number + 1
    assert offer.expires_after_cycle == cycle.number + 2
    accept(db, during_battle, offer)


def test_insufficient_second_fee_does_not_mutate_either_wallet(db, market):
    _, _, _, wallets, _, _, _ = market
    offer = create(db, market)
    wallets[1].wallet = {**wallets[1].wallet, 'gold': '0'}
    db.flush()
    before = [dict(w.wallet) for w in wallets]
    with pytest.raises(InsufficientFunds):
        accept(db, market, offer)
    assert [w.wallet for w in wallets] == before
    assert db.query(CycleMarketCaravan).count() == 0
    assert offer.status == 'pending'


def test_delivery_keeps_route_after_war_deletion_and_land_loss(db, market):
    service, cycle, clans, wallets, now, lands, _ = market
    offer = create(db, market)
    accept(db, market, offer)
    cars = db.query(CycleMarketCaravan).order_by(CycleMarketCaravan.id).all()
    snapshot = dict(cars[0].route)
    db.add(CycleDiplomacyPair(season_id=cycle.season_id, clan_low_id=clans[0].id,
        clan_high_id=clans[1].id, declarations={str(clans[0].id): {'last_cycle': None}}))
    clans[0].is_deleted = True
    for land in lands:
        land.owner_clan_id = None
    db.flush()
    for car in cars:
        wallet = next(w for w in wallets if w.clan_id == car.recipient_clan_id)
        args = dict(cycle_id=cycle.id, caravan_id=car.id, now=as_utc(car.arrives_at),
                    command_id=f'delivery:{car.id}', expected_revision=1, expected_wallet_revision=wallet.revision)
        with pytest.raises(ValueError, match='not due'):
            service.deliver(db, **{**args, 'now': now})
        service.deliver(db, **args)
        service.deliver(db, **args)
    assert cars[0].route == snapshot
    assert Decimal(wallets[0].wallet['wood']) == 33
    assert Decimal(wallets[1].wallet['iron']) == Decimal('32.5')
    assert len(wallets) == 3


def test_war_only_cancels_targeted_pair_public_offer_remains(db, market):
    service, cycle, clans, wallets, now, _, _ = market
    public = create(db, market)
    targeted = create(db, market, 'targeted', clans[1].id)
    neutral = create(db, market, 'neutral', clans[2].id)
    db.add(CycleDiplomacyPair(season_id=cycle.season_id, clan_low_id=clans[0].id,
        clan_high_id=clans[1].id, declarations={str(clans[0].id): {'last_cycle': None}}))
    db.flush()
    with pytest.raises(ValueError, match='Hostile'):
        accept(db, market, public)
    args = dict(cycle_id=cycle.id, clan_id=clans[0].id, other_clan_id=clans[1].id,
                now=now, command_id='war')
    assert service.cancel_hostile_pair(db, **args) == [targeted.id]
    service.cancel_hostile_pair(db, **args)
    assert public.status == neutral.status == 'pending'
    assert Decimal(wallets[0].wallet['iron']) == 25
    accept(db, market, public, recipient=2)


def test_expiry_after_second_full_cycle_not_calendar_hours(db, market):
    service, cycle, _, wallets, now, _, _ = market
    offer = create(db, market)
    assert offer.first_full_cycle == 1 and offer.expires_after_cycle == 2
    assert service.expire(db, cycle_id=cycle.id, now=now + timedelta(hours=25), command_id='early') == []
    cycle.number = 2
    cycle.settled_at = now + timedelta(days=10)
    db.flush()
    assert service.expire(db, cycle_id=cycle.id, now=as_utc(cycle.settled_at) - timedelta(seconds=1), command_id='before') == []
    assert service.expire(db, cycle_id=cycle.id, now=as_utc(cycle.settled_at), command_id='expiry') == [offer.id]
    service.expire(db, cycle_id=cycle.id, now=as_utc(cycle.settled_at), command_id='expiry2')
    assert Decimal(wallets[0].wallet['iron']) == 30


@pytest.mark.parametrize('cargo', [{'gold': 1}, {'iron': -1}, {'iron': 1.5}, {'iron': 'NaN'}, {}])
def test_invalid_terms(db, market, cargo):
    service, cycle, clans, _, now, _, _ = market
    with pytest.raises((ValueError, TypeError)):
        service.create(db, cycle_id=cycle.id, clan_id=clans[0].id, actor_id=10, offered=cargo,
            requested={'wood': 1}, now=now, command_id='invalid', expected_wallet_revision=1)


def test_actor_revision_command_collision_cancel_and_old_season(db, market):
    service, cycle, clans, wallets, now, _, season = market
    offer = create(db, market)
    args = dict(cycle_id=cycle.id, offer_id=offer.id, clan_id=clans[0].id, actor_id=99,
        now=now, command_id='cancel', expected_revision=1, expected_wallet_revision=wallets[0].revision)
    with pytest.raises(PermissionError):
        service.cancel(db, **args)
    db.add(ClanMember(clan_id=clans[0].id, user_id=99, is_trader=True))
    db.flush()
    with pytest.raises(EconomyConflict):
        service.cancel(db, **{**args, 'expected_revision': 0})
    with pytest.raises(ValueError, match='reused'):
        service.cancel(db, **{**args, 'command_id': 'create'})
    service.cancel(db, **args)
    service.cancel(db, **args)
    assert Decimal(wallets[0].wallet['iron']) == 30
    season.rules_snapshot = {'mechanics_version': 'legacy'}
    db.flush()
    with pytest.raises(ValueError, match='cycle_v1'):
        create(db, market, 'legacy')


def test_caller_rollback_removes_escrow_and_commands(db, market):
    create(db, market)
    db.rollback()
    assert db.query(CycleMarketOffer).count() == 0


def test_failure_between_wallet_writes_rolls_back_acceptance(db, market, monkeypatch):
    service, _, _, wallets, _, _, _ = market
    offer = create(db, market)
    before = [dict(w.wallet) for w in wallets]
    original = service.economy._write
    calls = []

    def fail_second(db, row, **values):
        calls.append(row.id)
        if len(calls) == 2:
            raise RuntimeError('injected storage failure')
        return original(db, row, **values)

    monkeypatch.setattr(service.economy, '_write', fail_second)
    with pytest.raises(RuntimeError):
        accept(db, market, offer)
    assert [w.wallet for w in wallets] == before
    assert offer.status == 'pending'
    assert db.query(CycleMarketCaravan).count() == 0


def test_real_route_requires_land_connection_or_both_ports(db, market, monkeypatch):
    from app.services.market_service import ClanMarketService

    service, _, clans, _, _, lands, _ = market
    monkeypatch.setattr(service, '_route', CycleMarketService._route.__get__(service))
    # No map edges or ports: no fabricated direct route.
    with pytest.raises(ValueError, match='route'):
        create(db, market, target=clans[1].id)
    lands[0].has_port = lands[1].has_port = True
    db.flush()
    offer = create(db, market, target=clans[1].id)
    accept(db, market, offer)
    car = db.query(CycleMarketCaravan).first()
    assert car.route['modes'] == ['sea']
    route = ClanMarketService()._best_route_between_clans(db, clans[0].id, clans[1].id)
    assert car.route['travel_hours'] == ClanMarketService.travel_hours(
        route, CampaignRuleService().get_active(db, create=False).values)


def test_rest_skips_partial_cycle_and_target_checks_hostility(db, market):
    service, cycle, clans, _, _, _, _ = market
    timeline = CampaignCycleStore.timeline(cycle)
    now = timeline.replay_deadline
    cycle.settled_at = now
    db.flush()
    rest_market = (*market[:4], now, *market[5:])
    offer = create(db, rest_market)
    assert (offer.first_full_cycle, offer.expires_after_cycle) == (2, 3)
    db.add(CycleDiplomacyPair(season_id=cycle.season_id, clan_low_id=clans[0].id,
        clan_high_id=clans[1].id, declarations={str(clans[1].id): {'last_cycle': None}}))
    db.flush()
    with pytest.raises(ValueError, match='nonhostile'):
        create(db, rest_market, 'hostile-target', clans[1].id)
