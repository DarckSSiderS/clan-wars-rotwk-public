from datetime import timedelta
from copy import deepcopy
from decimal import Decimal
from sqlalchemy import event

import pytest

from app.core.time import as_utc
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord, CampaignCyclePlan
from app.models.clan import Clan
from app.models.cycle_economy import CycleEconomyState, CycleEconomySnapshot
from app.models.cycle_income import CycleTerritoryProfile
from app.models.cycle_income import CycleIncomeAccrual
from app.models.cycle_battle import CycleTerritoryBattle, CycleOwnershipCorrection
from app.models.territory import TerritoryOwnershipHistory
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict
from app.services.cycle_battle_service import CycleBattleService
from app.services.cycle_income_service import CycleIncomeService
from app.services.cycle_ownership_service import CycleOwnershipService
from tests.test_cycle_campaign_api import client_for
from tests.test_cycle_ownership_service import completed


def correction_world(db):
    users, clan, other, land, cycle, battle, now = completed(db)
    CycleOwnershipService().apply_result(db, battle_id=battle.id, now=now)
    return users, clan, other, land, cycle, battle, now


def correct(db, world, **changes):
    users, clan, _, _, _, battle, now = world
    service = CycleOwnershipService()
    preview = service.preview_correction(db, battle_id=battle.id)
    args = dict(battle_id=battle.id, new_owner_clan_id=clan.id,
                preview_token=preview['preview_token'], command_id='ownership:1',
                actor_user_id=users[0].id, reason='Confirmed disputed result',
                now=now + timedelta(hours=1))
    args.update(changes)
    return service.correct_ownership(db, **args)


def test_explicit_correction_changes_map_from_now_and_keeps_confirmed_result(db):
    world = correction_world(db)
    users, clan, other, land, cycle, battle, now = world
    before = (battle.winner_clan_id, battle.recalculated_winner_clan_id, dict(cycle.dependencies))
    receipt = correct(db, world)
    assert land.owner_clan_id == clan.id
    assert as_utc(land.owned_since) == now + timedelta(hours=1)
    assert (land.fortifications, land.offense_level) == (3, 2)
    assert before == (battle.winner_clan_id, battle.recalculated_winner_clan_id, cycle.dependencies)
    assert receipt.previous_owner_clan_id == other.id
    assert receipt.new_owner_clan_id == clan.id
    assert receipt.actor_user_id == users[0].id
    assert receipt.reason == 'Confirmed disputed result'
    histories = db.query(TerritoryOwnershipHistory).filter_by(territory_id=land.id).order_by(TerritoryOwnershipHistory.id).all()
    assert as_utc(histories[-2].ended_at) == now + timedelta(hours=1)
    assert histories[-1].reason == 'cycle_admin_correction'
    assert histories[-1].clan_id == clan.id


def test_command_retry_is_exactly_once_even_after_a_later_owner_change(db):
    world = correction_world(db)
    service = CycleOwnershipService()
    users, clan, other, land, _, battle, now = world
    preview = service.preview_correction(db, battle_id=battle.id)
    first = correct(db, world)
    correct(db, world, new_owner_clan_id=other.id, command_id='ownership:2', now=now + timedelta(hours=2))
    count = db.query(TerritoryOwnershipHistory).count()
    again = correct(db, world, preview_token=preview['preview_token'], now=now + timedelta(hours=3))
    assert again.id == first.id
    assert land.owner_clan_id == other.id
    assert db.query(TerritoryOwnershipHistory).count() == count
    with pytest.raises(CycleConflict, match='command'):
        correct(db, world, preview_token=preview['preview_token'], reason='Changed payload')


def test_stale_preview_cannot_overwrite_a_later_cycle_or_owner(db):
    world = correction_world(db)
    _, _, other, land, cycle, battle, now = world
    service = CycleOwnershipService()
    preview = service.preview_correction(db, battle_id=battle.id)
    CampaignCycleStore().settle(db, cycle_id=cycle.id, completed_at=now)
    following = CampaignCycleStore().advance(db, cycle_id=cycle.id,
        now=now + timedelta(hours=12), rule_version=cycle.rule_version)
    with pytest.raises(CycleConflict, match='preview'):
        correct(db, world, preview_token=preview['preview_token'], now=now + timedelta(hours=12))
    fresh = service.preview_correction(db, battle_id=battle.id)
    assert fresh['current_cycle_id'] == following.id
    assert fresh['current_owner_clan_id'] == other.id
    correct(db, world, now=now + timedelta(hours=13))
    stale = service.preview_correction(db, battle_id=battle.id)
    correct(db, world, new_owner_clan_id=other.id, command_id='ownership:2', now=now + timedelta(hours=14))
    with pytest.raises(CycleConflict, match='preview'):
        correct(db, world, command_id='ownership:3', preview_token=stale['preview_token'], now=now + timedelta(hours=15))
    assert land.owner_clan_id == other.id


def test_preview_does_not_accrue_or_mutate_and_shows_actual_owner(db):
    world = correction_world(db)
    _, clan, other, land, _, battle, _ = world
    before = db.query(TerritoryOwnershipHistory).count()
    preview = CycleOwnershipService().preview_correction(db, battle_id=battle.id)
    assert preview['current_owner_clan_id'] == other.id
    assert preview['current_owner_name'] == other.name
    assert {row['clan_id'] for row in preview['choices']} == {None, clan.id, other.id}
    assert db.query(TerritoryOwnershipHistory).count() == before
    assert land.owner_clan_id == other.id


def test_advancement_during_lock_acquisition_invalidates_old_preview(db, monkeypatch):
    world = correction_world(db)
    _, _, other, land, cycle, battle, now = world
    preview = CycleOwnershipService().preview_correction(db, battle_id=battle.id)
    CampaignCycleStore().settle(db, cycle_id=cycle.id, completed_at=now)
    original = CycleIncomeService._cycles
    advanced = []
    def cycles_then_advance(session, season_id):
        rows = original(session, season_id)
        if not advanced:
            advanced.append(CampaignCycleStore().advance(session, cycle_id=cycle.id,
                now=now + timedelta(hours=12), rule_version=cycle.rule_version).id)
        return rows
    monkeypatch.setattr(CycleIncomeService, '_cycles', staticmethod(cycles_then_advance))
    with pytest.raises(CycleConflict, match='preview'):
        correct(db, world, preview_token=preview['preview_token'], now=now + timedelta(hours=13))
    assert land.owner_clan_id == other.id
    assert db.query(CycleOwnershipCorrection).count() == 0


@pytest.mark.parametrize('mode', ['unfinished', 'unapplied', 'closed', 'legacy', 'deleted', 'foreign', 'same', 'blank'])
def test_correction_rejects_invalid_context_without_changes(db, mode):
    world = correction_world(db)
    _, clan, other, land, cycle, battle, _ = world
    args = {}
    if mode == 'unfinished':
        battle.completed_at = None
    elif mode == 'unapplied':
        battle.ownership_applied_at = None
    elif mode == 'closed':
        db.get(CampaignSeason, cycle.season_id).status = 'completed'
    elif mode == 'legacy':
        db.get(CampaignSeason, cycle.season_id).rules_snapshot = {'mechanics_version': 'legacy'}
    elif mode == 'deleted':
        clan.is_deleted = True
    elif mode == 'foreign':
        foreign = Clan(name='Not a battle participant')
        db.add(foreign)
        db.flush()
        args['new_owner_clan_id'] = foreign.id
    elif mode == 'same':
        args['new_owner_clan_id'] = other.id
    else:
        args['reason'] = '   '
    db.flush()
    count = db.query(TerritoryOwnershipHistory).count()
    with pytest.raises(ValueError):
        correct(db, world, **args)
    assert land.owner_clan_id == other.id
    assert db.query(TerritoryOwnershipHistory).count() == count


def test_correction_accrues_old_owner_until_confirmation_and_new_owner_after(db):
    world = correction_world(db)
    _, clan, other, land, cycle, battle, now = world
    cycle.settled_at = now
    db.add(CycleTerritoryProfile(season_id=cycle.season_id, territory_id=land.id,
        base={'gold': '100', 'iron': '4', 'wood': '0', 'food': '0', 'mithril': '0'}, profile_material='iron'))
    states = []
    for owner in (clan, other):
        owner.created_at = now
        state = CycleEconomyState(season_id=cycle.season_id, clan_id=owner.id,
            wallet={k: '0' for k in ('gold', 'iron', 'wood', 'food', 'mithril')})
        db.add(state)
        states.append(state)
    db.flush()
    receipt = correct(db, world, now=now + timedelta(hours=12))
    assert Decimal(states[0].wallet['gold']) == 50
    assert Decimal(states[1].wallet['gold']) == 100
    CycleIncomeService().accrue(db, state_id=states[0].id, now=now + timedelta(hours=24))
    CycleIncomeService().accrue(db, state_id=states[1].id, now=now + timedelta(hours=24))
    assert Decimal(states[0].wallet['gold']) == 150
    assert Decimal(states[1].wallet['gold']) == 150
    assert as_utc(receipt.applied_at) == now + timedelta(hours=12)


def test_failure_after_transfer_rolls_back_income_history_and_receipt(db, monkeypatch):
    world = correction_world(db)
    _, _, other, land, _, _, _ = world
    db.commit()
    count = db.query(TerritoryOwnershipHistory).count()
    def fail(*args, **kwargs):
        raise ValueError('Recalculation failed')
    monkeypatch.setattr(CycleOwnershipService, '_recalculate', fail)
    with pytest.raises(ValueError, match='Recalculation failed'):
        correct(db, world)
    assert land.owner_clan_id == other.id
    assert db.query(TerritoryOwnershipHistory).count() == count


def test_failure_after_receipt_flush_restores_all_income_history_and_revisions(db):
    world = correction_world(db)
    _, clan, other, land, cycle, _, now = world
    cycle.settled_at = now
    clan.created_at = other.created_at = now
    db.add(CycleTerritoryProfile(season_id=cycle.season_id, territory_id=land.id,
        base={'gold': '100', 'iron': '0', 'wood': '0', 'food': '0', 'mithril': '0'}, profile_material=None))
    states = [CycleEconomyState(season_id=cycle.season_id, clan_id=owner.id,
        wallet={k: '0' for k in ('gold', 'iron', 'wood', 'food', 'mithril')}) for owner in (clan, other)]
    db.add_all(states)
    db.commit()
    before_wallets = [(s.id, deepcopy(s.wallet), s.revision) for s in states]
    before_history = [(r.id, r.clan_id, r.started_at, r.ended_at) for r in db.query(TerritoryOwnershipHistory).order_by(TerritoryOwnershipHistory.id)]
    revision = cycle.revision
    def fail_after_receipt(session, context):
        if any(isinstance(row, CycleOwnershipCorrection) for row in session.new):
            raise ValueError('Failure after receipt insertion')
    event.listen(db, 'after_flush', fail_after_receipt)
    try:
        with pytest.raises(ValueError, match='Failure after receipt insertion'):
            correct(db, world, now=now + timedelta(hours=12))
    finally:
        event.remove(db, 'after_flush', fail_after_receipt)
    assert land.owner_clan_id == other.id
    assert db.connection().exec_driver_sql('SELECT revision FROM campaign_cycles WHERE id = ?', (cycle.id,)).scalar_one() == revision
    assert cycle.revision == revision
    assert [(s.id, s.wallet, s.revision) for s in states] == before_wallets
    assert [(r.id, r.clan_id, r.started_at, r.ended_at) for r in db.query(TerritoryOwnershipHistory).order_by(TerritoryOwnershipHistory.id)] == before_history
    assert db.query(CycleIncomeAccrual).count() == 0
    assert db.query(CycleOwnershipCorrection).count() == 0


def test_old_battle_correction_preserves_populated_later_cycle_and_actual_owner(db):
    world = correction_world(db)
    users, clan, other, land, cycle, battle, now = world
    CampaignCycleStore().settle(db, cycle_id=cycle.id, completed_at=now)
    following = CampaignCycleStore().advance(db, cycle_id=cycle.id, now=now + timedelta(hours=12), rule_version=cycle.rule_version)
    later_time = CampaignCycleStore.timeline(following).replay_deadline
    third = Clan(name='Later owner', created_at=later_time)
    db.add(third)
    db.flush()
    plan = CampaignCyclePlan(cycle_id=following.id, clan_id=clan.id,
        orders=[{'user_id': users[0].id, 'kind': 'attack', 'territory_id': land.id}],
        snapshot={'member_ids': [users[0].id], 'allied_clan_ids': []},
        frozen_at=CampaignCycleStore.timeline(following).battle_at)
    state = CycleEconomyState(season_id=cycle.season_id, clan_id=clan.id,
        wallet={k: '0' for k in ('gold', 'iron', 'wood', 'food', 'mithril')})
    clan.created_at = later_time
    db.add_all([plan, state])
    db.flush()
    economic = CycleEconomySnapshot(cycle_id=following.id, state_id=state.id,
        effects=[{'key': 'white_tree', 'level': 1, 'effect': 'gold', 'percent': '15'}],
        territory_upgrades={str(land.id): {'gold': 2}}, state_revision=state.revision,
        frozen_at=CampaignCycleStore.timeline(following).battle_at)
    later_battle = CycleTerritoryBattle(cycle_id=following.id, territory_id=land.id,
        owner_clan_id=other.id, winner_clan_id=third.id, recalculated_winner_clan_id=third.id,
        sides=[{'clan_id': other.id, 'user_ids': []}, {'clan_id': third.id, 'user_ids': []}],
        completed_at=later_time, ownership_applied_at=later_time)
    db.add_all([economic, later_battle])
    CycleOwnershipService._transfer(db, land, third.id, db.get(CampaignSeason, cycle.season_id), later_time)
    previous = db.query(TerritoryOwnershipHistory).filter_by(clan_id=other.id).one()
    before = deepcopy((plan.orders, plan.snapshot, economic.effects, economic.territory_upgrades,
        later_battle.sides, later_battle.winner_clan_id, later_battle.recalculated_winner_clan_id,
        previous.started_at, previous.ended_at))
    receipt = correct(db, world, now=later_time)
    assert receipt.previous_owner_clan_id == third.id
    assert receipt.current_cycle_id == following.id
    assert before == (plan.orders, plan.snapshot, economic.effects, economic.territory_upgrades,
        later_battle.sides, later_battle.winner_clan_id, later_battle.recalculated_winner_clan_id,
        previous.started_at, previous.ended_at)
    assert battle.winner_clan_id == other.id


def test_neutral_correction_closes_ownership_without_creating_a_neutral_clan(db):
    world = correction_world(db)
    _, _, other, land, _, _, now = world
    other.base_influence = 100
    other.territory_points = 125
    land.influence_value = 25
    receipt = correct(db, world, new_owner_clan_id=None)
    assert land.owner_clan_id is None
    assert land.owned_since is None
    assert receipt.new_owner_clan_id is None
    assert not db.query(TerritoryOwnershipHistory).filter_by(territory_id=land.id, ended_at=None).count()
    assert other.territory_points == 100


def test_owner_correction_api_is_admin_only_and_requires_fresh_preview(db, monkeypatch):
    world = correction_world(db)
    users, clan, _, land, _, battle, now = world
    db.commit()
    monkeypatch.setattr('app.api.v1.cycle_campaign.utc_now', lambda: now + timedelta(hours=1))
    url = f'/cycles/battles/{battle.id}/ownership'
    ordinary = client_for(db, users[2])
    assert ordinary.get(url).status_code in (401, 403)
    assert ordinary.post(url, json={}).status_code in (401, 403)
    admin = client_for(db, users[0], admin=True)
    response = admin.get(url)
    assert response.status_code == 200
    payload = dict(new_owner_clan_id=clan.id, reason='Verified correction', command_id='api:1',
                   preview_token=response.json()['preview_token'])
    assert admin.post(url, json=payload).status_code == 200
    assert land.owner_clan_id == clan.id
    assert admin.post(url, json=payload).status_code == 200
    detail = admin.get(f'/cycles/battles/{battle.id}').json()
    assert detail['ownership_corrections'][0]['new_owner_clan_id'] == clan.id
    assert detail['current_owner_clan_id'] == clan.id
    assert detail['ownership_applied_at'] is not None
