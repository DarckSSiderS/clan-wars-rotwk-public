from datetime import timedelta

import pytest

from app.core.time import as_utc
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_battle_service import CycleBattleService
from app.services.cycle_settlement_service import CycleSettlementService
from tests.test_cycle_battle_service import revealed
from tests.test_cycle_ownership_service import completed


def test_applies_ownership_before_rest_and_retry_does_not_restart_rest(db):
    _, _, other, land, cycle, battle, now = completed(db)
    service = CycleSettlementService()
    service.settle(db, cycle_id=cycle.id, now=now)
    assert land.owner_clan_id == other.id
    assert battle.ownership_applied_at is not None
    settled = cycle.settled_at
    revision = cycle.revision
    service.settle(db, cycle_id=cycle.id, now=now + timedelta(hours=1))
    assert as_utc(cycle.settled_at) == as_utc(settled)
    assert cycle.revision == revision
    assert CampaignCycleStore.timeline(cycle).next_cycle(rule_version=cycle.rule_version).preparation_at == now + timedelta(hours=12)


def test_unresolved_interception_blocks_all_territory_finalization(db):
    _, _, _, land, cycle, battle, now = completed(db)
    owner = land.owner_clan_id
    CampaignCycleStore().register_dependency(db, cycle_id=cycle.id, key='interception:pending')
    with pytest.raises(ValueError, match='Interception'):
        CycleSettlementService().settle(db, cycle_id=cycle.id, now=now)
    assert land.owner_clan_id == owner
    assert cycle.settled_at is None
    assert battle.ownership_applied_at is None


def test_failed_ownership_application_rolls_back_new_calculation(db):
    _, _, _, _, cycle = revealed(db)
    battle = CycleBattleService().create_from_orders(db, cycle_id=cycle.id)[0]
    now = CampaignCycleStore.timeline(cycle).replay_deadline
    CampaignCycleStore().mark_import_complete(db, cycle_id=cycle.id, verified_at=now)
    # Missing frozen rule set must not leave a partially finalized battle.
    with pytest.raises(ValueError, match='rule version'):
        CycleSettlementService().settle(db, cycle_id=cycle.id, now=now)
    db.refresh(battle)
    db.refresh(cycle)
    assert battle.completed_at is None
    assert battle.ownership_applied_at is None
    assert cycle.settled_at is None


def test_complete_import_and_reveal_are_mandatory_even_when_no_battles(db):
    _, _, _, _, cycle = revealed(db)
    now = CampaignCycleStore.timeline(cycle).replay_deadline
    with pytest.raises(ValueError, match='import'):
        CycleSettlementService().settle(db, cycle_id=cycle.id, now=now)
    assert cycle.settled_at is None
