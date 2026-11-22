from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.campaign import CampaignSeason
from app.models.clan import Clan, ClanMember
from app.models.territory import Territory
from app.models.cycle_economy import CycleEconomyState, CycleEconomySnapshot, CycleTerritoryUpgrade
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_economy import Resources, START_RESOURCES, InsufficientFunds
from app.services.cycle_economy_store import CycleEconomyStore, EconomyConflict


NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


@pytest.fixture
def economy(db):
    season = CampaignSeason(number=1, name='Economy', status='active', starts_at=NOW,
                            rules_snapshot={'version': 1, 'mechanics_version': 'cycle_v1'})
    clan = Clan(name='Test', leader_id=10)
    db.add_all([season, clan])
    db.flush()
    cycle = CampaignCycleStore().start(db, season_id=season.id)
    store = CycleEconomyStore()
    state = store.ensure_state(db, season_id=season.id, clan_id=clan.id)
    return store, state, cycle, clan, season


def test_starter_once_opt_in_and_rollback(db, economy):
    store, state, cycle, clan, season = economy
    assert store.balance(state) == START_RESOURCES
    assert store.ensure_state(db, season_id=season.id, clan_id=clan.id).id == state.id
    assert db.query(CycleEconomyState).count() == 1
    season.rules_snapshot = {'mechanics_version': 'legacy'}
    db.flush()
    with pytest.raises(ValueError, match='cycle_v1'):
        store.ensure_state(db, season_id=season.id, clan_id=clan.id)
    db.rollback()
    assert db.query(CycleEconomyState).count() == 0


def test_starters_late_once_and_head_only(db, economy):
    store, state, cycle, clan, _ = economy
    with pytest.raises(PermissionError):
        store.choose_starters(db, state_id=state.id, actor_id=99, selected=['white_tree', 'merchant_guild'], expected_revision=1)
    store.choose_starters(db, state_id=state.id, actor_id=10, selected=['white_tree', 'merchant_guild'], expected_revision=1)
    assert state.relics == {'white_tree': 1, 'merchant_guild': 1}
    assert state.active_relics == []
    with pytest.raises(EconomyConflict):
        store.choose_starters(db, state_id=state.id, actor_id=10, selected=['white_tree', 'dwarf_anvil'], expected_revision=1)
    with pytest.raises(ValueError, match='already'):
        store.choose_starters(db, state_id=state.id, actor_id=10, selected=['white_tree', 'dwarf_anvil'], expected_revision=2)


def test_market_authorization_decimal_and_stale(db, economy):
    store, state, _, clan, _ = economy
    db.add(ClanMember(clan_id=clan.id, user_id=20, is_trader=True))
    db.flush()
    store.market(db, state_id=state.id, actor_id=20, resource='iron', quantity='0.1', buying=True, expected_revision=1)
    assert store.balance(state).gold == Decimal('995.5')
    assert state.wallet['iron'] == '30.1'
    with pytest.raises(EconomyConflict):
        store.market(db, state_id=state.id, actor_id=10, resource='iron', quantity=1, buying=True, expected_revision=1)
    with pytest.raises(PermissionError):
        store.buy_relic(db, state_id=state.id, actor_id=20, key='white_tree', expected_revision=2)
    with pytest.raises(InsufficientFunds):
        store.buy_relic(db, state_id=state.id, actor_id=10, key='white_tree', expected_revision=2)
    assert state.revision == 2


def test_loadout_and_immutable_reveal(db, economy):
    store, state, cycle, _, _ = economy
    store.choose_starters(db, state_id=state.id, actor_id=10, selected=['white_tree', 'merchant_guild'], expected_revision=1)
    args = dict(state_id=state.id, actor_id=10, cycle_id=cycle.id, selected=['merchant_guild'], expected_revision=2)
    with pytest.raises(ValueError):
        store.select_active(db, now=NOW, **args)
    prep = CampaignCycleStore().timeline(cycle).preparation_at
    store.select_active(db, now=prep, **args)
    reveal = CampaignCycleStore().timeline(cycle).battle_at
    with pytest.raises(ValueError):
        store.freeze_snapshot(db, state_id=state.id, cycle_id=cycle.id, now=prep, expected_revision=3)
    snap = store.freeze_snapshot(db, state_id=state.id, cycle_id=cycle.id, now=reveal, expected_revision=3)
    state.relics = {**state.relics, 'merchant_guild': 3}
    db.flush()
    assert snap.effects[0]['percent'] == '10'
    assert store.freeze_snapshot(db, state_id=state.id, cycle_id=cycle.id, now=reveal, expected_revision=4).id == snap.id
    assert db.query(CycleEconomySnapshot).count() == 1


def test_upgrade_ownership_payment_and_rollback(db, economy):
    store, state, _, clan, _ = economy
    land = Territory(name='Land', region='R', svg_path_data='', owner_clan_id=clan.id)
    db.add(land)
    db.flush()
    store.buy_upgrade(db, state_id=state.id, actor_id=10, territory_id=land.id, branch='gold', expected_revision=1, expected_upgrade_revision=0)
    assert db.get(CycleTerritoryUpgrade, (state.season_id, land.id)).levels['gold'] == 1
    assert store.balance(state).gold == 700
    land.owner_clan_id = None
    db.flush()
    with pytest.raises(PermissionError):
        store.buy_upgrade(db, state_id=state.id, actor_id=10, territory_id=land.id, branch='gold', expected_revision=2, expected_upgrade_revision=1)
    assert state.revision == 2
    assert land.development_level == 0


def test_late_starters_and_relic_upgrade_without_influence(db, economy):
    store, state, cycle, clan, _ = economy
    cycle.settled_at = CampaignCycleStore.timeline(cycle).replay_deadline
    clan.base_influence = 0
    state.wallet = store._wallet(Resources(100000, 1000, 1000, 1000, 1000))
    db.flush()
    store.choose_starters(db, state_id=state.id, actor_id=10,
                          selected=['merchant_guild', 'white_tree'], expected_revision=1)
    store.buy_relic(db, state_id=state.id, actor_id=10, key='merchant_guild', expected_revision=2)
    store.buy_relic(db, state_id=state.id, actor_id=10, key='merchant_guild', expected_revision=3)
    before = dict(state.wallet)
    with pytest.raises(ValueError):
        store.buy_relic(db, state_id=state.id, actor_id=10, key='merchant_guild', expected_revision=4)
    assert state.wallet == before
    assert state.relics['merchant_guild'] == 3


def test_upgrade_bounds_and_caller_rollback(db, economy):
    store, state, _, clan, _ = economy
    land = Territory(name='Bounds', region='R', svg_path_data='', owner_clan_id=clan.id)
    db.add(land)
    state.wallet = store._wallet(Resources(100000, 1000, 1000, 1000, 1000))
    db.commit()
    baseline = dict(state.wallet)
    for revision in range(1, 4):
        store.buy_upgrade(db, state_id=state.id, actor_id=10, territory_id=land.id,
                          branch='gold', expected_revision=revision, expected_upgrade_revision=revision - 1)
    with pytest.raises(ValueError):
        store.buy_upgrade(db, state_id=state.id, actor_id=10, territory_id=land.id,
                          branch='gold', expected_revision=4, expected_upgrade_revision=3)
    db.rollback()
    assert store.balance(state) == Resources(**baseline)
    assert db.get(CycleTerritoryUpgrade, (state.season_id, land.id)) is None


def test_revoked_trader_checked_in_database(db, economy):
    from sqlalchemy import update
    store, state, _, clan, _ = economy
    member = ClanMember(clan_id=clan.id, user_id=20, is_trader=True)
    db.add(member)
    db.flush()
    db.execute(update(ClanMember).where(ClanMember.id == member.id).values(is_trader=False)
               .execution_options(synchronize_session=False))
    with pytest.raises(PermissionError):
        store.market(db, state_id=state.id, actor_id=20, resource='iron', quantity=1,
                     buying=False, expected_revision=1)


def test_frozen_discount_does_not_follow_relic_upgrades(db, economy):
    store, state, cycle, clan, _ = economy
    state.wallet = store._wallet(Resources(100000, 1000, 1000, 1000, 1000))
    state.relics = {'merchant_guild': 1}
    state.active_relics = ['merchant_guild']
    land = Territory(name='Discount', region='R', svg_path_data='', owner_clan_id=clan.id)
    db.add(land)
    db.flush()
    store.freeze_snapshot(db, state_id=state.id, cycle_id=cycle.id,
                          now=CampaignCycleStore.timeline(cycle).battle_at, expected_revision=1)
    store.buy_relic(db, state_id=state.id, actor_id=10, key='merchant_guild', expected_revision=2)
    before = store.balance(state).gold
    store.buy_upgrade(db, state_id=state.id, actor_id=10, territory_id=land.id,
                      branch='gold', expected_revision=3, expected_upgrade_revision=0)
    assert before - store.balance(state).gold == Decimal('270')


@pytest.mark.parametrize('selected', [['white_tree', 'white_tree'], ['unknown', 'white_tree'], ['white_tree']])
def test_invalid_starters_leave_receipt_and_wallet_unchanged(db, economy, selected):
    store, state, _, _, _ = economy
    with pytest.raises(ValueError):
        store.choose_starters(db, state_id=state.id, actor_id=10, selected=selected, expected_revision=1)
    assert state.revision == 1
    assert not state.starters_chosen
    assert store.balance(state) == START_RESOURCES


@pytest.mark.parametrize('selected', [['white_tree'] * 2, ['unknown'],
    ['white_tree', 'merchant_guild', 'dwarf_anvil', 'ents_seed', 'mordor_forge']])
def test_invalid_active_sets_are_not_saved(db, economy, selected):
    store, state, cycle, _, _ = economy
    state.relics = dict.fromkeys(['white_tree', 'merchant_guild', 'dwarf_anvil', 'ents_seed', 'mordor_forge'], 1)
    db.flush()
    with pytest.raises(ValueError):
        store.select_active(db, state_id=state.id, actor_id=10, cycle_id=cycle.id,
                            now=CampaignCycleStore.timeline(cycle).preparation_at,
                            selected=selected, expected_revision=1)
    assert state.active_relics == []
    assert state.revision == 1


def test_land_revision_and_frozen_levels(db, economy):
    store, state, cycle, clan, _ = economy
    state.wallet = store._wallet(Resources(100000, 1000, 1000, 1000, 1000))
    land = Territory(name='Snapshot', region='R', svg_path_data='', owner_clan_id=clan.id)
    db.add(land)
    db.flush()
    store.buy_upgrade(db, state_id=state.id, actor_id=10, territory_id=land.id,
                      branch='offense', expected_revision=1, expected_upgrade_revision=0)
    with pytest.raises(EconomyConflict):
        store.buy_upgrade(db, state_id=state.id, actor_id=10, territory_id=land.id,
                          branch='offense', expected_revision=2, expected_upgrade_revision=0)
    snap = store.freeze_snapshot(db, state_id=state.id, cycle_id=cycle.id,
                                now=CampaignCycleStore.timeline(cycle).battle_at, expected_revision=2)
    store.buy_upgrade(db, state_id=state.id, actor_id=10, territory_id=land.id,
                      branch='offense', expected_revision=3, expected_upgrade_revision=1)
    assert snap.territory_upgrades[str(land.id)] == {'offense': 1}
    assert db.get(CycleTerritoryUpgrade, (state.season_id, land.id)).levels == {'offense': 2}


def test_rest_can_change_loadout_and_uses_live_discount(db, economy):
    store, state, cycle, clan, _ = economy
    state.relics = {'merchant_guild': 1}
    db.flush()
    cycle.settled_at = CampaignCycleStore.timeline(cycle).replay_deadline
    db.flush()
    store.select_active(db, state_id=state.id, actor_id=10, cycle_id=cycle.id,
                        now=CampaignCycleStore.timeline(cycle).settled_at,
                        selected=['merchant_guild'], expected_revision=1)
    assert state.active_relics == ['merchant_guild']


@pytest.mark.parametrize('branch,resource,output,port', [
    ('profile', None, 1, False),
    ('profile', 'mithril', 1, False),
    ('profile', 'gold', 1, False),
    ('profile', 'iron', 0, False),
    ('mithril', 'iron', 1, False),
    ('mithril', None, 1, False),
    ('mithril', 'mithril', 0, False),
    ('naval', 'wood', 1, False),
])
def test_upgrade_rejects_ineligible_terrain_without_spending(db, economy, branch, resource, output, port):
    store, state, _, clan, _ = economy
    land = Territory(name='Ineligible', region='R', svg_path_data='', owner_clan_id=clan.id,
                     resource_type=resource, resource_output=output, has_port=port, is_coastal=True)
    db.add(land)
    db.flush()
    # SQLAlchemy applies the legacy iron default on INSERT for None; persist an
    # actual missing profile rather than accidentally testing that default.
    land.resource_type = resource
    db.flush()
    before = dict(state.wallet)
    with pytest.raises(ValueError, match='profile|mithril|port'):
        store.buy_upgrade(db, state_id=state.id, actor_id=10, territory_id=land.id,
                          branch=branch, expected_revision=1, expected_upgrade_revision=0)
    assert state.wallet == before
    assert state.revision == 1
    assert db.get(CycleTerritoryUpgrade, (state.season_id, land.id)) is None


@pytest.mark.parametrize('branch,resource,port', [
    ('profile', 'iron', False), ('profile', 'wood', False), ('profile', 'food', False),
    ('mithril', 'mithril', False), ('naval', None, True),
])
def test_upgrade_accepts_matching_terrain(db, economy, branch, resource, port):
    store, state, _, clan, _ = economy
    land = Territory(name='Eligible', region='R', svg_path_data='', owner_clan_id=clan.id,
                     resource_type=resource, resource_output=1, has_port=port)
    db.add(land)
    db.flush()
    store.buy_upgrade(db, state_id=state.id, actor_id=10, territory_id=land.id,
                      branch=branch, expected_revision=1, expected_upgrade_revision=0)
    assert db.get(CycleTerritoryUpgrade, (state.season_id, land.id)).levels == {branch: 1}
    assert state.revision == 2


@pytest.mark.parametrize('operation', ['select_active', 'freeze_snapshot'])
def test_cycle_lock_precedes_wallet_and_season_locks(db, economy, operation):
    from sqlalchemy import event
    store, state, cycle, _, _ = economy
    locked_tables = []

    def record_lock(execute_state):
        statement = execute_state.statement
        if getattr(statement, '_for_update_arg', None) is not None:
            locked_tables.extend(table.name for table in statement.get_final_froms())

    event.listen(db, 'do_orm_execute', record_lock)
    try:
        args = dict(state_id=state.id, cycle_id=cycle.id, expected_revision=1)
        if operation == 'select_active':
            store.select_active(db, actor_id=10, selected=[],
                                now=CampaignCycleStore.timeline(cycle).preparation_at, **args)
        else:
            store.freeze_snapshot(db, now=CampaignCycleStore.timeline(cycle).battle_at, **args)
    finally:
        event.remove(db, 'do_orm_execute', record_lock)
    assert locked_tables[0] == 'campaign_cycles'
    assert locked_tables.index('campaign_cycles') < locked_tables.index('cycle_economy_states')
