"""Параллельные команды новых циклов на отдельной настоящей PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from uuid import UUID

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.campaign_rules import default_campaign_rule_values
from app.models.campaign import CampaignRuleSet
from app.models.campaign_cycle import CampaignCyclePlan, CampaignCyclePlanRevision
from app.models.cycle_battle import CycleMatchContribution
from app.models.cycle_economy import CycleEconomyState
from app.models.cycle_income import CycleIncomeAccrual
from app.models.cycle_market import CycleMarketCaravan
from app.models.territory import Territory, TerritoryOwnershipHistory
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict
from app.services.cycle_economy import Resources
from app.services.cycle_economy_store import CycleEconomyStore, EconomyConflict
from app.services.cycle_income_service import CycleIncomeService
from app.services.cycle_market_service import CycleMarketService
from app.services.cycle_match_service import CycleMatchService, ReplayFacts, ReplayPlayer
from app.services.cycle_orders import Order
from app.services.cycle_plan_service import CyclePlanService
from app.services.cycle_reveal_service import CycleRevealService
from tests.test_campaign_cycle_store import START
from tests.test_cycle_reveal_service import prepared


def world(db):
    users, home, away, land, cycle, _ = prepared(db)
    home.created_at = away.created_at = START
    other = Territory(name='Проверка торговли PostgreSQL', region='Local', svg_path_data='M0 0',
        owner_clan_id=away.id, is_playable=True, resource_type='iron', resource_output=4)
    db.add(other)
    db.add(CampaignRuleSet(version=cycle.rule_version, values=default_campaign_rule_values(),
        is_active=True, reason='Изолированная приёмка PostgreSQL'))
    db.flush()
    land.adjacent_territory_ids, other.adjacent_territory_ids = [other.id], [land.id]
    land.resource_type, land.resource_output = 'iron', 4
    for territory in (land, other):
        CycleIncomeService().configure_profile(db, season_id=cycle.season_id, territory_id=territory.id,
            base=Resources(100, iron=4), profile_material='iron', now=START)
        db.add(TerritoryOwnershipHistory(territory_id=territory.id,
            clan_id=territory.owner_clan_id, started_at=START))
    wallets = [CycleEconomyStore().ensure_state(db, season_id=cycle.season_id, clan_id=c.id) for c in (home, away)]
    db.commit()
    return users, home, away, land, cycle, wallets


def parallel(db, action):
    factory, barrier = sessionmaker(bind=db.bind, autoflush=False), Barrier(2, timeout=10)

    def run(index):
        with factory() as session:
            barrier.wait()
            try:
                value = action(session, index)
                session.commit()
                return 'ok', value
            except (CycleConflict, EconomyConflict) as error:
                session.rollback()
                return 'conflict', type(error).__name__

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(run, index) for index in range(2)]
        return [job.result(timeout=20) for job in jobs]


def test_postgres_same_wallet_version_cannot_buy_twice(postgres_db):
    db = postgres_db
    users, _, _, _, _, wallets = world(db)
    state_id, actor, revision = wallets[0].id, users[0].id, wallets[0].revision
    before = Resources(**wallets[0].wallet)
    db.commit()

    def buy(session, _):
        return CycleEconomyStore().market(session, state_id=state_id, actor_id=actor,
            resource='wood', quantity=1, buying=True, expected_revision=revision).id

    result = parallel(db, buy)
    assert sorted(status for status, _ in result) == ['conflict', 'ok']
    db.expire_all()
    after = Resources(**db.get(CycleEconomyState, state_id).wallet)
    assert after.wood == before.wood + 1 and after.gold < before.gold


def test_postgres_income_for_same_period_is_credited_once(postgres_db):
    db = postgres_db
    _, _, _, _, _, wallets = world(db)
    state_id = wallets[0].id
    before = Resources(**wallets[0].wallet)
    db.commit()
    parallel(db, lambda session, _: CycleIncomeService().accrue(
        session, state_id=state_id, now=START + timedelta(days=1)))
    db.expire_all()
    assert Resources(**db.get(CycleEconomyState, state_id).wallet) == before + Resources(200, 6, 2, 2)
    assert db.query(CycleIncomeAccrual).filter_by(state_id=state_id).count() == 1


def test_postgres_competing_orders_keep_one_revision(postgres_db):
    db = postgres_db
    users, home, _, land, cycle, _ = world(db)
    cycle_id, clan_id, actor_id, land_id = cycle.id, home.id, users[0].id, land.id
    player_ids = (users[1].id, users[2].id)
    now = CampaignCycleStore.timeline(cycle).preparation_at
    revision = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle_id, clan_id=clan_id).one().revision
    db.commit()
    result = parallel(db, lambda session, index: CyclePlanService().save(session,
        cycle_id=cycle_id, clan_id=clan_id, actor_user_id=actor_id, expected_revision=revision,
        orders=[Order(player_ids[index], 'defend', land_id)], now=now).revision)
    assert sorted(status for status, _ in result) == ['conflict', 'ok']
    db.expire_all()
    plan = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle_id, clan_id=clan_id).one()
    assert plan.revision == revision + 1
    assert db.query(CampaignCyclePlanRevision).filter_by(plan_id=plan.id, revision=revision + 1).count() == 1


@pytest.mark.parametrize('same_command', [True, False])
def test_postgres_parallel_accept_retry_creates_only_two_caravans(postgres_db, same_command):
    db = postgres_db
    users, home, away, _, cycle, wallets = world(db)
    now = CampaignCycleStore.timeline(cycle).preparation_at
    service = CycleMarketService()
    offer = service.create(db, cycle_id=cycle.id, clan_id=home.id, actor_id=users[0].id,
        offered={'iron': 2}, requested={'wood': 3}, now=now, command_id='pg:create',
        expected_wallet_revision=wallets[0].revision)
    arguments = dict(cycle_id=cycle.id, offer_id=offer.id, clan_id=away.id, actor_id=users[3].id,
        now=now, command_id='pg:accept', expected_revision=offer.revision,
        expected_sender_revision=wallets[0].revision, expected_wallet_revision=wallets[1].revision)
    before = [Resources(**wallet.wallet) for wallet in wallets]
    state_ids = [wallet.id for wallet in wallets]
    db.commit()
    result = parallel(db, lambda session, index: CycleMarketService().accept(session,
        **{**arguments, 'command_id': arguments['command_id'] if same_command else f'pg:accept:{index}'}).id)
    assert sorted(status for status, _ in result) == (['ok', 'ok'] if same_command else ['conflict', 'ok'])
    db.expire_all()
    assert db.query(CycleMarketCaravan).filter_by(offer_id=offer.id).count() == 2
    balances = [Resources(**db.get(CycleEconomyState, key).wallet) for key in state_ids]
    assert balances[0].iron == before[0].iron and balances[1].wood == before[1].wood - 3
    assert balances[0].gold == before[0].gold - 12
    assert balances[1].gold == before[1].gold - Decimal('9')


def test_postgres_parallel_replay_import_has_one_personal_contribution(postgres_db):
    db = postgres_db
    users, home, away, _, cycle, _ = world(db)
    start = CampaignCycleStore.timeline(cycle).battle_at
    battle = CycleRevealService().reveal(db, cycle_id=cycle.id, now=start)[0]
    facts = ReplayFacts('postgres-replay', 'bfmeladder', 'ennorath', True,
        start + timedelta(minutes=10), start + timedelta(minutes=20),
        (ReplayPlayer(str(UUID(int=users[2].id)), 1, 1000, True, 'ennorath'),
         ReplayPlayer(str(UUID(int=users[3].id)), 2, 1000, True, 'ennorath')), 2)
    battle_id, winner_id, loser_id = battle.id, away.id, home.id
    db.commit()
    parallel(db, lambda session, _: len(CycleMatchService().process(session, battle_id=battle_id, replay=facts)))
    db.expire_all()
    rows = db.query(CycleMatchContribution).filter_by(battle_id=battle_id).all()
    assert len(rows) == 2
    assert {row.clan_id: row.points for row in rows} == {winner_id: Decimal(200), loser_id: Decimal(-100)}
