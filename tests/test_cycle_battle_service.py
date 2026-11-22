from decimal import Decimal

import pytest

from app.models.campaign_cycle import CampaignCyclePlan
from app.models.clan import Clan
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_battle_service import CycleBattleService
from app.services.cycle_plan_service import CyclePlanService
from app.services.cycle_orders import Order
from tests.test_cycle_plan_service import setup_world


def revealed(db):
    users, clan, land, cycle = setup_world(db)
    plans = CyclePlanService()
    timeline = CampaignCycleStore.timeline(cycle)
    plans.capture_preparation(db, cycle_id=cycle.id, now=timeline.preparation_at)
    plans.save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
               expected_revision=0, orders=[Order(users[2].id, 'defend', land.id)], now=timeline.preparation_at)
    plans.freeze(db, cycle_id=cycle.id, now=timeline.battle_at)
    # Fixture represents another clan's already validated and frozen plan.
    other = Clan(name='Other', level=1)
    db.add(other)
    db.flush()
    db.add(CampaignCyclePlan(cycle_id=cycle.id, clan_id=other.id, revision=1,
           orders=[{'user_id': users[3].id, 'kind': 'attack', 'territory_id': land.id,
                    'source_id': None, 'route': 'land'}], frozen_at=timeline.battle_at,
           snapshot={'level': 1, 'member_ids': [users[3].id], 'allied_clan_ids': []}))
    db.flush()
    return users, clan, other, land, cycle


def test_reveal_creates_one_battle_per_land_with_all_sides_and_dependency(db):
    users, clan, other, land, cycle = revealed(db)
    service = CycleBattleService()
    rows = service.create_from_orders(db, cycle_id=cycle.id)
    assert len(rows) == 1
    assert {s['clan_id'] for s in rows[0].sides} == {clan.id, other.id}
    assert service.create_from_orders(db, cycle_id=cycle.id)[0].id == rows[0].id
    assert f'territory:{rows[0].id}' in cycle.dependencies


def test_cannot_create_battles_before_orders_are_frozen(db):
    _, _, _, cycle = setup_world(db)
    with pytest.raises(ValueError):
        CycleBattleService().create_from_orders(db, cycle_id=cycle.id)


def test_points_are_idempotent_and_completed_battle_correction_keeps_owner(db):
    users, clan, other, land, cycle = revealed(db)
    service = CycleBattleService()
    battle = service.create_from_orders(db, cycle_id=cycle.id)[0]
    service.record_contribution(db, battle_id=battle.id, replay_id='arena:1', user_id=users[3].id,
                                clan_id=other.id, points=Decimal('100.125'), reason='counted')
    service.record_contribution(db, battle_id=battle.id, replay_id='arena:1', user_id=users[3].id,
                                clan_id=other.id, points=Decimal('100.125'), reason='counted')
    assert service.scores(db, battle.id)[other.id] == Decimal('100.125')
    deadline = CampaignCycleStore.timeline(cycle).replay_deadline
    CampaignCycleStore().mark_import_complete(db, cycle_id=cycle.id, verified_at=deadline)
    service.finalize(db, battle_id=battle.id, completed_at=deadline)
    assert battle.winner_clan_id == other.id
    service.review_contribution(db, battle_id=battle.id, replay_id='arena:1', user_id=users[3].id,
                                 counted=False, actor_user_id=users[0].id, reason='Invalid match')
    assert service.scores(db, battle.id)[other.id] == 0
    assert battle.winner_clan_id == other.id
    assert battle.recalculated_winner_clan_id == clan.id


def test_manual_points_require_reason_and_do_not_duplicate_command(db):
    users, clan, other, land, cycle = revealed(db)
    service = CycleBattleService()
    battle = service.create_from_orders(db, cycle_id=cycle.id)[0]
    with pytest.raises(ValueError):
        service.adjust(db, battle_id=battle.id, clan_id=other.id, amount=10,
                       command_id='admin:1', actor_user_id=users[0].id, reason='')
    for _ in range(2):
        service.adjust(db, battle_id=battle.id, clan_id=other.id, amount=10,
                       command_id='admin:1', actor_user_id=users[0].id, reason='Correction')
    assert service.scores(db, battle.id)[other.id] == 10


def test_repeating_fraction_reimport_survives_commit_and_reload(db):
    users, clan, other, land, cycle = revealed(db)
    service = CycleBattleService()
    battle = service.create_from_orders(db, cycle_id=cycle.id)[0]
    points = Decimal(100) / 3
    row = service.record_contribution(db, battle_id=battle.id, replay_id='fraction', user_id=users[3].id,
                                     clan_id=other.id, points=points, reason='counted')
    first_id = row.id
    db.commit()
    db.expire_all()
    repeated = service.record_contribution(db, battle_id=battle.id, replay_id='fraction', user_id=users[3].id,
                                          clan_id=other.id, points=points, reason='counted')
    assert repeated.id == first_id
