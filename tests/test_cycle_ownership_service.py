from datetime import timedelta

import pytest

from app.core.campaign_rules import default_campaign_rule_values
from app.models.campaign import CampaignRuleSet
from app.models.territory import TerritoryOwnershipHistory
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_battle_service import CycleBattleService
from app.services.cycle_ownership_service import CycleOwnershipService
from tests.test_cycle_battle_service import revealed


def completed(db):
    users, clan, other, land, cycle = revealed(db)
    db.add(CampaignRuleSet(version=cycle.rule_version, values=default_campaign_rule_values(),
                           is_active=True, reason='Test cycle rules'))
    db.flush()
    battle = CycleBattleService().create_from_orders(db, cycle_id=cycle.id)[0]
    land.fortifications = 3
    land.offense_level = 2
    CycleBattleService().record_contribution(db, battle_id=battle.id, replay_id='win',
        user_id=users[3].id, clan_id=other.id, points=100, reason='counted')
    now = CampaignCycleStore.timeline(cycle).replay_deadline
    CampaignCycleStore().mark_import_complete(db, cycle_id=cycle.id, verified_at=now)
    CycleBattleService().finalize(db, battle_id=battle.id, completed_at=now)
    return users, clan, other, land, cycle, battle, now


def test_calculation_cannot_finish_cycle_before_ownership_is_applied(db):
    _, clan, other, land, cycle, battle, now = completed(db)
    with pytest.raises(ValueError, match='dependencies'):
        CampaignCycleStore().settle(db, cycle_id=cycle.id, completed_at=now)
    service = CycleOwnershipService()
    service.apply_result(db, battle_id=battle.id, now=now)
    assert land.owner_clan_id == other.id
    assert (land.fortifications, land.offense_level) == (3, 2)
    before = db.query(TerritoryOwnershipHistory).count()
    service.apply_result(db, battle_id=battle.id, now=now + timedelta(hours=1))
    assert db.query(TerritoryOwnershipHistory).count() == before
    CampaignCycleStore().settle(db, cycle_id=cycle.id, completed_at=now)


def test_score_review_does_not_reapply_confirmed_ownership(db):
    users, clan, other, land, cycle, battle, now = completed(db)
    service = CycleOwnershipService()
    service.apply_result(db, battle_id=battle.id, now=now)
    CycleBattleService().review_contribution(db, battle_id=battle.id, replay_id='win', user_id=users[3].id,
        counted=False, actor_user_id=users[0].id, reason='Review')
    service.apply_result(db, battle_id=battle.id, now=now + timedelta(hours=1))
    assert land.owner_clan_id == other.id
    assert battle.recalculated_winner_clan_id == clan.id


def test_changed_owner_requires_explicit_admin_action_not_silent_overwrite(db):
    _, _, _, land, _, battle, now = completed(db)
    land.owner_clan_id = None
    db.flush()
    with pytest.raises(ValueError, match='owner'):
        CycleOwnershipService().apply_result(db, battle_id=battle.id, now=now)
