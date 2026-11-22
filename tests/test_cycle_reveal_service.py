from uuid import UUID

import pytest

from app.models.campaign_cycle import CampaignCyclePlan
from app.models.clan import Clan, ClanMember
from app.models.cycle_battle import CycleTerritoryBattle
from app.models.cycle_diplomacy import CycleDiplomacyEvent, CycleDiplomacyPair
from app.models.cycle_reinforcement_state import CycleReinforcementState
from app.models.external_identity import ExternalPlayerIdentity
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_orders import Order
from app.services.cycle_plan_service import CyclePlanService
from app.services.cycle_reveal_service import CycleRevealService
from tests.test_cycle_plan_service import setup_world


def prepared(db, *, neutral=False):
    users, home, land, cycle = setup_world(db)
    away = Clan(name='Invaders', leader_id=users[3].id, level=1)
    db.add(away)
    db.flush()
    db.add(ClanMember(clan_id=away.id, user_id=users[3].id, joined_at=cycle.starts_at))
    for identity in db.query(ExternalPlayerIdentity).all():
        identity.external_uuid = str(UUID(int=identity.user_id))
    db.add(ExternalPlayerIdentity(user_id=users[3].id, source='bfmeladder',
        external_uuid=str(UUID(int=users[3].id)), current_nickname=users[3].username,
        verification_status='verified'))
    if neutral:
        land.owner_clan_id = None
    db.flush()
    plans = CyclePlanService()
    timeline = CampaignCycleStore.timeline(cycle)
    plans.capture_preparation(db, cycle_id=cycle.id, now=timeline.preparation_at)
    plans.save(db, cycle_id=cycle.id, clan_id=home.id, actor_user_id=users[0].id,
        expected_revision=0, orders=[] if neutral else [Order(users[2].id, 'defend', land.id)],
        now=timeline.preparation_at)
    plans.save(db, cycle_id=cycle.id, clan_id=away.id, actor_user_id=users[3].id,
        expected_revision=0, orders=[Order(users[3].id, 'attack', land.id)], now=timeline.preparation_at)
    return users, home, away, land, cycle, timeline.battle_at


def test_reveal_creates_battles_reserves_and_hostility_once(db):
    _, home, away, _, cycle, now = prepared(db)
    service = CycleRevealService()
    service.reveal(db, cycle_id=cycle.id, now=now)
    assert cycle.orders_frozen_at is not None and cycle.battles_registered
    assert db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle.id).count() == 1
    assert db.query(CycleReinforcementState).filter_by(cycle_id=cycle.id).count() == 1
    pair = db.query(CycleDiplomacyPair).one()
    assert pair.declarations[str(away.id)]['last_cycle'] == str(cycle.number)
    assert str(home.id) not in pair.declarations
    revision = cycle.revision
    service.reveal(db, cycle_id=cycle.id, now=now)
    assert cycle.revision == revision
    assert db.query(CycleDiplomacyEvent).filter_by(kind='attack_revealed').count() == 1


def test_neutral_land_does_not_create_diplomatic_enemy(db):
    _, _, _, _, cycle, now = prepared(db, neutral=True)
    CycleRevealService().reveal(db, cycle_id=cycle.id, now=now)
    assert db.query(CycleTerritoryBattle).count() == 1
    assert db.query(CycleDiplomacyEvent).count() == 0


def test_hidden_attack_is_not_revealed_early(db):
    _, _, _, _, cycle, _ = prepared(db)
    with pytest.raises(ValueError):
        CycleRevealService().reveal(db, cycle_id=cycle.id,
            now=CampaignCycleStore.timeline(cycle).preparation_at)
    assert db.query(CycleDiplomacyEvent).count() == 0
    assert db.query(CycleTerritoryBattle).count() == 0


def test_failed_reserve_initialization_rolls_back_entire_reveal(db):
    users, _, _, _, cycle, now = prepared(db)
    db.query(ExternalPlayerIdentity).filter_by(user_id=users[3].id).one().external_uuid = 'invalid'
    db.flush()
    with pytest.raises(ValueError):
        CycleRevealService().reveal(db, cycle_id=cycle.id, now=now)
    db.refresh(cycle)
    assert cycle.orders_frozen_at is None and not cycle.battles_registered
    assert db.query(CycleTerritoryBattle).count() == 0
    assert db.query(CycleDiplomacyEvent).count() == 0
    assert all(plan.frozen_at is None for plan in db.query(CampaignCyclePlan).all())
