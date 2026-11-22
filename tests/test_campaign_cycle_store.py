from datetime import datetime, timedelta, timezone

import pytest

from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict
from app.services.campaign_cycle_service import CyclePhase


START = datetime(2026, 10, 15, tzinfo=timezone.utc)


def season(db, *, enabled=True):
    row = CampaignSeason(number=1, name='Local test', status='active',
                         starts_at=START,
                         rules_snapshot={'version': 2, 'mechanics_version': 'cycle_v1' if enabled else 'legacy'})
    db.add(row)
    db.flush()
    return row


def prepare(db, row):
    from app.services.cycle_plan_service import CyclePlanService
    from app.services.cycle_battle_service import CycleBattleService
    timeline = CampaignCycleStore.timeline(row)
    plans = CyclePlanService()
    plans.capture_preparation(db, cycle_id=row.id, now=timeline.preparation_at)
    plans.freeze(db, cycle_id=row.id, now=timeline.battle_at)
    CycleBattleService().create_from_orders(db, cycle_id=row.id)


def test_first_cycle_is_persisted_once_and_cannot_change_rules(db):
    owner = season(db)
    service = CampaignCycleStore()
    first = service.start(db, season_id=owner.id)
    assert service.start(db, season_id=owner.id).id == first.id
    assert db.query(CampaignCycleRecord).count() == 1
    assert service.timeline(first).rule_version == 2
    assert service.timeline(first).phase_at(START) == CyclePhase.REGISTRATION
    db.commit()
    db.expire_all()
    assert service.timeline(db.get(CampaignCycleRecord, first.id)).battle_at == START + timedelta(hours=96)


def test_late_worker_starts_a_full_preparation_instead_of_inventing_missed_cycle(db):
    owner = season(db)
    service = CampaignCycleStore()
    first = service.start(db, season_id=owner.id)
    prepare(db, first)
    completed_at = service.timeline(first).replay_deadline
    service.mark_import_complete(db, cycle_id=first.id, verified_at=completed_at)
    service.settle(db, cycle_id=first.id, completed_at=completed_at)
    restarted_at = completed_at + timedelta(days=3)
    next_cycle = service.advance(db, cycle_id=first.id, now=restarted_at, rule_version=first.rule_version)
    assert service.timeline(next_cycle).preparation_at == restarted_at
    assert service.timeline(next_cycle).battle_at == restarted_at + timedelta(hours=24)
    assert db.query(CampaignCycleRecord).count() == 2


def test_old_season_requires_explicit_opt_in(db):
    owner = season(db, enabled=False)
    with pytest.raises(ValueError, match='cycle_v1'):
        CampaignCycleStore().start(db, season_id=owner.id)
    assert db.query(CampaignCycleRecord).count() == 0


def test_settlement_requires_import_and_all_registered_dependencies(db):
    owner = season(db)
    service = CampaignCycleStore()
    row = service.start(db, season_id=owner.id)
    prepare(db, row)
    deadline = service.timeline(row).replay_deadline
    service.register_dependency(db, cycle_id=row.id, key='territory:14')
    service.register_dependency(db, cycle_id=row.id, key='interception:2')
    with pytest.raises(ValueError, match='import'):
        service.settle(db, cycle_id=row.id, completed_at=deadline)
    service.mark_import_complete(db, cycle_id=row.id, verified_at=deadline)
    with pytest.raises(ValueError, match='dependencies'):
        service.settle(db, cycle_id=row.id, completed_at=deadline)
    service.complete_dependency(db, cycle_id=row.id, key='territory:14')
    service.complete_dependency(db, cycle_id=row.id, key='interception:2')
    service.settle(db, cycle_id=row.id, completed_at=deadline + timedelta(hours=9))
    frozen = service.timeline(row).settled_at
    service.settle(db, cycle_id=row.id, completed_at=deadline + timedelta(days=2))
    assert service.timeline(row).settled_at == frozen
    with pytest.raises(ValueError):
        service.register_dependency(db, cycle_id=row.id, key='territory:15')


def test_import_cannot_be_verified_before_full_replay_window(db):
    owner = season(db)
    service = CampaignCycleStore()
    row = service.start(db, season_id=owner.id)
    with pytest.raises(ValueError):
        service.mark_import_complete(db, cycle_id=row.id,
                                     verified_at=service.timeline(row).battle_ends_at)


def test_next_cycle_is_not_started_early_or_duplicated_after_outage(db):
    owner = season(db)
    service = CampaignCycleStore()
    row = service.start(db, season_id=owner.id)
    prepare(db, row)
    recovered_at = service.timeline(row).replay_deadline + timedelta(days=3)
    service.mark_import_complete(db, cycle_id=row.id, verified_at=recovered_at)
    service.settle(db, cycle_id=row.id, completed_at=recovered_at)
    with pytest.raises(ValueError):
        service.advance(db, cycle_id=row.id, now=recovered_at, rule_version=3)
    following = service.advance(db, cycle_id=row.id, now=recovered_at + timedelta(hours=12), rule_version=3)
    assert service.advance(db, cycle_id=row.id, now=recovered_at + timedelta(days=5), rule_version=3).id == following.id
    assert service.timeline(following).battle_at == recovered_at + timedelta(hours=36)
    assert db.query(CampaignCycleRecord).count() == 2


def test_manual_end_is_persisted_and_disallows_a_following_cycle(db):
    owner = season(db)
    service = CampaignCycleStore()
    row = service.start(db, season_id=owner.id)
    prepare(db, row)
    service.request_end(db, cycle_id=row.id)
    deadline = service.timeline(row).replay_deadline
    service.mark_import_complete(db, cycle_id=row.id, verified_at=deadline)
    service.settle(db, cycle_id=row.id, completed_at=deadline)
    assert service.timeline(row).phase_at(deadline) == CyclePhase.SEASON_ENDED
    with pytest.raises(ValueError):
        service.advance(db, cycle_id=row.id, now=deadline + timedelta(days=1), rule_version=2)


def test_unknown_dependency_is_not_silently_created(db):
    owner = season(db)
    service = CampaignCycleStore()
    row = service.start(db, season_id=owner.id)
    with pytest.raises(ValueError):
        service.complete_dependency(db, cycle_id=row.id, key='typo:1')


def test_stale_expected_revision_is_rejected(db):
    owner = season(db)
    service = CampaignCycleStore()
    row = service.start(db, season_id=owner.id)
    revision = row.revision
    service.request_end(db, cycle_id=row.id, expected_revision=revision)
    with pytest.raises(CycleConflict):
        service.request_end(db, cycle_id=row.id, expected_revision=revision)


def test_import_alone_cannot_certify_missing_battle_enumeration(db):
    owner = season(db)
    service = CampaignCycleStore()
    row = service.start(db, season_id=owner.id)
    deadline = service.timeline(row).replay_deadline
    service.mark_import_complete(db, cycle_id=row.id, verified_at=deadline)
    with pytest.raises(ValueError, match='battle'):
        service.settle(db, cycle_id=row.id, completed_at=deadline)
