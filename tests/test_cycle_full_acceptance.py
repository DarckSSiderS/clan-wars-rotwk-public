"""Сквозная приёмка на синтетических проверенных рейтингах, без запросов к Арене."""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.core.campaign_rules import default_campaign_rule_values
from app.core.time import as_utc
from app.models.campaign import CampaignRuleSet
from app.models.cycle_battle import CycleTerritoryBattle
from app.models.cycle_market import CycleMarketCaravan
from app.models.territory import Territory, TerritoryOwnershipHistory
from app.services.arena_replay_scan import ArenaReplayScan
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_arena_ingestion_service import CycleArenaIngestionService
from app.services.cycle_economy import Resources
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_income_service import CycleIncomeService
from app.services.cycle_interception_service import CycleInterceptionService
from app.services.cycle_market_service import CycleMarketService
from app.services.cycle_match_service import CycleMatchService, ReplayFacts, ReplayPlayer
from app.services.cycle_settlement_service import CycleSettlementService
from tests.test_cycle_interception_service import setup
from tests.test_cycle_reinforcement_store import T


@pytest.mark.parametrize('database', ['db', 'postgres_db'])
def test_full_cycle_trade_interception_points_ownership_income_and_next_preparation(request, database):
    db = request.getfixturevalue(database)
    # Один и тот же сценарий выполняется с настоящими ограничениями PostgreSQL и SQLite.
    from tests.test_cycle_reinforcement_store import world as make_world
    actors = make_world.__wrapped__(db)
    users, clans, land, cycle = actors
    start = T - timedelta(hours=96)
    db.add(CampaignRuleSet(version=cycle.rule_version, values=default_campaign_rule_values(),
        is_active=True, reason='Сквозная изолированная приёмка'))
    other = Territory(name='Торговая земля приёмки', region='Local', svg_path_data='M0 0',
        owner_clan_id=clans[0].id, is_playable=True, resource_type='iron', resource_output=4)
    db.add(other)
    db.flush()
    land.adjacent_territory_ids, other.adjacent_territory_ids = [other.id], [land.id]
    for clan in clans:
        clan.created_at = start
    wallets = [CycleEconomyStore().ensure_state(db, season_id=cycle.season_id, clan_id=clan.id) for clan in clans]
    for territory in (land, other):
        CycleIncomeService().configure_profile(db, season_id=cycle.season_id, territory_id=territory.id,
            base=Resources(100, iron=4), profile_material='iron', now=start)
        db.add(TerritoryOwnershipHistory(territory_id=territory.id,
            clan_id=territory.owner_clan_id, started_at=start))
    db.flush()

    # Подкрепление попадает в засаду; её очки существуют отдельно от территории.
    interception = setup(db, actors, origin_territory_id=other.id)
    from app.models.cycle_dispatch_route import CycleDispatchRoute
    route = db.query(CycleDispatchRoute).filter_by(cycle_id=cycle.id, dispatch_id='d').one()
    assert route.snapshot['territory_ids'] == [other.id, land.id]
    for wallet in wallets:
        CycleEconomyStore().freeze_snapshot(db, state_id=wallet.id, cycle_id=cycle.id,
            now=T, expected_revision=wallet.revision)
    CycleInterceptionService().process(db, cycle_id=cycle.id, dispatch_id='d', replay=interception)

    market = CycleMarketService()
    offer = market.create(db, cycle_id=cycle.id, clan_id=clans[0].id, actor_id=users[0].id,
        offered={'iron': 2}, requested={'wood': 3}, now=T, command_id='acceptance:offer',
        expected_wallet_revision=wallets[0].revision)
    market.accept(db, cycle_id=cycle.id, offer_id=offer.id, clan_id=clans[1].id, actor_id=users[3].id,
        now=T, command_id='acceptance:accept', expected_revision=offer.revision,
        expected_sender_revision=wallets[0].revision, expected_wallet_revision=wallets[1].revision)
    caravans = db.query(CycleMarketCaravan).filter_by(offer_id=offer.id).all()
    assert len(caravans) == 2
    for caravan in caravans:
        wallet = next(w for w in wallets if w.clan_id == caravan.recipient_clan_id)
        args = dict(cycle_id=cycle.id, caravan_id=caravan.id, now=as_utc(caravan.arrives_at),
            command_id=f'acceptance:deliver:{caravan.id}', expected_revision=caravan.revision,
            expected_wallet_revision=wallet.revision)
        market.deliver(db, **args)
        before = dict(wallet.wallet)
        market.deliver(db, **args)
        assert wallet.wallet == before

    match_service = CycleMatchService()
    battle = db.query(CycleTerritoryBattle).one()
    for index in range(2):
        match_service.process(db, battle_id=battle.id, replay=ReplayFacts(
            f'acceptance:ordinary:{index}', 'bfmeladder', 'ennorath', True,
            T + timedelta(hours=1 + index * 2), T + timedelta(hours=1 + index * 2, minutes=10),
            (ReplayPlayer(str(UUID(int=6)), 1, 600, True, 'ennorath'),
             ReplayPlayer(str(UUID(int=8)), 2, 1000, True, 'ennorath')), 1))

    first_end = T + timedelta(hours=14, minutes=5)
    verification = CycleArenaIngestionService().verify_pending(db,
        scan=ArenaReplayScan(T, first_end, 'synthetic-acceptance:interception'), now=first_end)
    assert verification['interceptions_settled'] == 1
    helper_game = ReplayFacts('acceptance:helper', 'bfmeladder', 'ennorath', True,
        T + timedelta(hours=25), T + timedelta(hours=25, minutes=10),
        (ReplayPlayer(str(UUID(int=2)), 1, 1000, True, 'ennorath'),
         ReplayPlayer(str(UUID(int=6)), 2, 1000, True, 'ennorath')), 1)
    contributions = match_service.process(db, battle_id=battle.id, replay=helper_game)
    assert {row.clan_id: row.points for row in contributions} == {clans[1].id: Decimal(100), clans[2].id: Decimal(-100)}
    match_service.process(db, battle_id=battle.id, replay=helper_game)

    deadline = CampaignCycleStore.timeline(cycle).replay_deadline
    CycleArenaIngestionService().verify_pending(db,
        scan=ArenaReplayScan(T, deadline, 'synthetic-acceptance:whole-cycle'), now=deadline)
    CycleSettlementService().settle(db, cycle_id=cycle.id, now=deadline)
    assert land.owner_clan_id == clans[2].id
    assert battle.winner_clan_id == clans[2].id
    before_retry = [dict(w.wallet) for w in wallets]
    CycleSettlementService().settle(db, cycle_id=cycle.id, now=deadline)
    assert [w.wallet for w in wallets] == before_retry
    assert CycleIncomeService().accrue(db, state_id=wallets[2].id, now=deadline + timedelta(days=1)) == Resources(200, 6, 2, 2)
    assert CycleIncomeService().accrue(db, state_id=wallets[1].id, now=deadline + timedelta(days=1)) == Resources(100, 2, 2, 2)
    following = CampaignCycleStore().advance(db, cycle_id=cycle.id, now=deadline + timedelta(hours=12),
        rule_version=cycle.rule_version)
    assert as_utc(following.preparation_at) == deadline + timedelta(hours=12)
    db.rollback()
