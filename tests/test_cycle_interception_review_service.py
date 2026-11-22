import importlib
import importlib.util
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.cycle_interception import CycleInterception, CycleInterceptionContribution
from app.models.cycle_battle import CycleMatchContribution
from app.services.cycle_reinforcement_store import CycleReinforcementStore
from tests.test_cycle_interception_service import setup, process, verify, finish, service as accounting
from tests.test_cycle_reinforcement_store import world, T


def reviewer(monkeypatch, now=None):
    name = 'app.services.cycle_interception_review_service'
    assert importlib.util.find_spec(name), 'Нет сервиса административного пересмотра'
    module = importlib.import_module(name)
    monkeypatch.setattr(module, 'utc_now', lambda: now or T + timedelta(hours=15))
    return module.CycleInterceptionReviewService()


def args(db, world, command='review-1', **extra):
    return dict(cycle_id=world[3].id, dispatch_id='d', actor_user_id=world[0][7].id,
        expected_revision=db.query(CycleInterception).one().revision,
        command_id=command, reason='Проверено администратором', **extra)


def resolved(db, world):
    facts = setup(db, world)
    process(db, world, facts)
    verify(db, world)
    finish(db, world)
    return facts


def dispatch(db, world):
    return CycleReinforcementStore()._locked(db, world[3].id)[2].dispatches[0]


def test_review_changes_history_only_and_source_cannot_overwrite_it(db, world, monkeypatch):
    facts = resolved(db, world)
    svc = reviewer(monkeypatch)
    original = dispatch(db, world)
    command = args(db, world, replay_id='bfmeladder:interception-game', user_id=world[0][1].id, counted=False)
    result = svc.review_contribution(db, **command)
    assert result['revision'] == command['expected_revision'] + 1
    assert dispatch(db, world) == original
    row = db.query(CycleInterceptionContribution).filter_by(user_id=world[0][1].id).one()
    assert row.counted and row.review_counted is False
    with pytest.raises(ValueError, match='review'):
        process(db, world, replace(facts, winning_team=2))
    process(db, world, facts)
    assert row.review_counted is False and row.points == 200
    view = accounting().read(db, cycle_id=world[3].id, dispatch_id='d', now=T + timedelta(hours=15))
    assert Decimal(view['sides'][0]['score']) == 0
    assert view['applied_result']['help_score'] == '200'
    assert svc.review_contribution(db, **command) == result
    audit = importlib.import_module('app.models.cycle_interception').CycleInterceptionReviewCommand
    assert db.query(audit).count() == 1
    with pytest.raises(ValueError):
        svc.review_contribution(db, **{**command, 'counted': True})


def test_adjustment_does_not_fabricate_elo_and_can_follow_missing_elo(db, world, monkeypatch):
    facts = setup(db, world)
    process(db, world, replace(facts, players=tuple(replace(p, historical=False) for p in facts.players)))
    svc = reviewer(monkeypatch)
    with pytest.raises(ValueError, match='Elo'):
        svc.review_contribution(db, **args(db, world, replay_id='bfmeladder:interception-game',
            user_id=world[0][1].id, counted=True))
    before = deepcopy(db.query(CycleInterceptionContribution).first().calculation)
    svc.adjust(db, **args(db, world, side_clan_id=world[1][0].id, amount='125.5'))
    view = accounting().read(db, cycle_id=world[3].id, dispatch_id='d', now=T + timedelta(hours=15))
    assert Decimal(view['sides'][0]['score']) == Decimal('125.5')
    assert len(view['adjustments']) == 1
    assert db.query(CycleInterceptionContribution).first().calculation == before
    assert before['historical_elo'] is None
    assert dispatch(db, world).outcome.value == 'pending'


def test_preview_confirm_is_separate_and_keeps_first_applied_result(db, world, monkeypatch):
    resolved(db, world)
    svc = reviewer(monkeypatch)
    svc.adjust(db, **args(db, world, side_clan_id=world[1][2].id, amount='1000'))
    assert dispatch(db, world).outcome.value == 'exhausted'
    preview = svc.preview_outcome(db, **args(db, world, command='preview-1'))
    assert preview['proposed_result']['outcome'] == 'blocked'
    assert dispatch(db, world).outcome.value == 'exhausted'
    confirm = args(db, world, command='confirm-1', preview_command_id='preview-1')
    result = svc.confirm_outcome(db, **confirm)
    assert result['applied_result']['outcome'] == dispatch(db, world).outcome.value == 'blocked'
    record = db.query(CycleInterception).one()
    assert record.original_applied_result['outcome'] == 'exhausted'
    assert db.query(CycleMatchContribution).count() == 0
    assert svc.confirm_outcome(db, **confirm) == result
    svc.adjust(db, **args(db, world, command='adjust-2', side_clan_id=world[1][2].id, amount='-1000'))
    svc.preview_outcome(db, **args(db, world, command='preview-2'))
    svc.confirm_outcome(db, **args(db, world, command='confirm-2', preview_command_id='preview-2'))
    assert dispatch(db, world).outcome.value == 'exhausted'
    assert record.original_applied_result['outcome'] == 'exhausted'
    audit = importlib.import_module('app.models.cycle_interception').CycleInterceptionReviewCommand
    assert {r.action for r in db.query(audit)} == {'adjust', 'preview_outcome', 'confirm_outcome'}
    assert all(r.reason and r.before and r.after for r in db.query(audit))


@pytest.mark.parametrize('offset', [0, 1, 86400])
def test_actual_clock_rejects_confirmation_at_or_after_arrival_but_allows_history(db, world, monkeypatch, offset):
    resolved(db, world)
    svc = reviewer(monkeypatch)
    svc.adjust(db, **args(db, world, side_clan_id=world[1][2].id, amount='1000'))
    svc.preview_outcome(db, **args(db, world, command='preview'))
    confirm = args(db, world, command='confirm', preview_command_id='preview')
    svc = reviewer(monkeypatch, T + timedelta(hours=24, seconds=offset))
    with pytest.raises(ValueError, match='прибыт'):
        svc.confirm_outcome(db, **confirm)
    assert dispatch(db, world).outcome.value == 'exhausted'
    svc.adjust(db, **args(db, world, command='after-arrival', side_clan_id=world[1][0].id, amount='2'))
    with pytest.raises(ValueError, match='прибыт'):
        svc.preview_outcome(db, **args(db, world, command='late-preview'))


def test_stale_revision_and_changed_aggregate_reject_preview_confirmation(db, world, monkeypatch):
    resolved(db, world)
    svc = reviewer(monkeypatch)
    old = args(db, world, side_clan_id=world[1][0].id, amount='3')
    svc.adjust(db, **old)
    with pytest.raises(ValueError):
        svc.adjust(db, **{**old, 'command_id': 'stale'})
    svc.preview_outcome(db, **args(db, world, command='preview'))
    confirm = args(db, world, command='confirm', preview_command_id='preview')
    row = CycleReinforcementStore()._locked(db, world[3].id)[1]
    row.revision += 1
    db.flush()
    with pytest.raises(ValueError, match='измен'):
        svc.confirm_outcome(db, **confirm)


def test_territory_points_before_arrival_fail_closed_and_rollback(db, world, monkeypatch):
    from app.models.cycle_battle import CycleTerritoryBattle
    resolved(db, world)
    svc = reviewer(monkeypatch)
    svc.adjust(db, **args(db, world, side_clan_id=world[1][2].id, amount='1000'))
    svc.preview_outcome(db, **args(db, world, command='preview'))
    battle = db.query(CycleTerritoryBattle).one()
    db.add(CycleMatchContribution(battle_id=battle.id, replay_id='invalid-early-help',
        user_id=world[0][1].id, clan_id=world[1][1].id, points=1, counted=True, reason='counted'))
    db.flush()
    with pytest.raises(ValueError, match='территориаль'):
        svc.confirm_outcome(db, **args(db, world, command='confirm', preview_command_id='preview'))
    assert dispatch(db, world).outcome.value == 'exhausted'


def test_review_checks_only_frozen_bindings_not_names_or_live_identity(db, world, monkeypatch):
    from app.models.external_identity import ExternalPlayerIdentity
    resolved(db, world)
    svc = reviewer(monkeypatch)
    world[0][1].username = 'renamed-review-player'
    world[0][1].display_name = world[0][7].username
    db.query(ExternalPlayerIdentity).filter_by(user_id=world[0][1].id).one().external_uuid = 'broken-live-value'
    db.flush()
    svc.review_contribution(db, **args(db, world, replay_id='bfmeladder:interception-game',
        user_id=world[0][1].id, counted=False))
    with pytest.raises(ValueError):
        svc.review_contribution(db, **args(db, world, command='outsider', replay_id='bfmeladder:interception-game',
            user_id=world[0][7].id, counted=False))


def test_admin_can_read_before_first_import_without_creating_a_record(db, world, monkeypatch):
    setup(db, world)
    result = reviewer(monkeypatch).read(db, cycle_id=world[3].id, dispatch_id='d')
    assert result['revision'] is None and result['audit'] == []
    assert db.query(CycleInterception).count() == 0


def test_history_changes_do_not_block_source_finalization_after_arrival(db, world, monkeypatch):
    process(db, world, setup(db, world))
    verify(db, world)
    svc = reviewer(monkeypatch)
    svc.adjust(db, **args(db, world, side_clan_id=world[1][2].id, amount='1000'))
    svc.review_contribution(db, **args(db, world, command='exclude-helper',
        replay_id='bfmeladder:interception-game', user_id=world[0][1].id, counted=False))
    result = accounting().settle_ready(db, cycle_id=world[3].id, now=T + timedelta(hours=25))
    assert len(result) == 1
    assert dispatch(db, world).outcome.value == 'exhausted'
    assert dispatch(db, world).help_score == 200
    assert dict(dispatch(db, world).ambush_scores) == {world[1][2].id: Decimal(-100)}
    history = accounting().read(db, cycle_id=world[3].id, dispatch_id='d', now=T + timedelta(hours=25))
    assert Decimal(history['sides'][0]['score']) == 0
    assert Decimal(history['sides'][1]['score']) == 900
    assert history['original_applied_result']['outcome'] == 'exhausted'
    assert world[3].dependencies['interception:d'] is True


def test_initial_outcome_can_be_applied_by_explicit_preview_confirm(db, world, monkeypatch):
    process(db, world, setup(db, world))
    verify(db, world)
    svc = reviewer(monkeypatch)
    svc.adjust(db, **args(db, world, side_clan_id=world[1][2].id, amount='1000'))
    svc.preview_outcome(db, **args(db, world, command='preview'))
    svc.confirm_outcome(db, **args(db, world, command='confirm', preview_command_id='preview'))
    assert dispatch(db, world).outcome.value == 'blocked'
    assert finish(db, world).outcome.value == 'blocked'


def test_confirmation_rejects_history_change_and_uses_clock_after_lock(db, world, monkeypatch):
    resolved(db, world)
    svc = reviewer(monkeypatch)
    svc.preview_outcome(db, **args(db, world, command='preview'))
    svc.adjust(db, **args(db, world, side_clan_id=world[1][0].id, amount='1'))
    with pytest.raises(ValueError, match='измен'):
        svc.confirm_outcome(db, **args(db, world, command='stale', preview_command_id='preview'))
    svc.preview_outcome(db, **args(db, world, command='new-preview'))
    lock = svc._locked

    def after_lock(*arguments):
        result = lock(*arguments)
        reviewer(monkeypatch, T + timedelta(hours=24))
        return result

    monkeypatch.setattr(svc, '_locked', after_lock)
    with pytest.raises(ValueError, match='прибыт'):
        svc.confirm_outcome(db, **args(db, world, command='late', preview_command_id='new-preview'))


def test_confirmation_failure_rolls_back_state_audit_revision_and_keeps_caller_work(db, world, monkeypatch):
    resolved(db, world)
    svc = reviewer(monkeypatch)
    svc.adjust(db, **args(db, world, side_clan_id=world[1][2].id, amount='1000'))
    svc.preview_outcome(db, **args(db, world, command='preview'))
    original = dispatch(db, world)
    record = db.query(CycleInterception).one()
    revision = record.revision
    aggregate = CycleReinforcementStore()._locked(db, world[3].id)[1]
    aggregate_revision = aggregate.revision
    write = CycleReinforcementStore._write

    def fail_after_write(self, *arguments):
        write(self, *arguments)
        raise RuntimeError('Отказ после сохранения состояния')

    monkeypatch.setattr(CycleReinforcementStore, '_write', fail_after_write)
    with pytest.raises(RuntimeError):
        svc.confirm_outcome(db, **args(db, world, command='confirm', preview_command_id='preview'))
    assert dispatch(db, world) == original
    assert record.revision == revision and aggregate.revision == aggregate_revision
    model = importlib.import_module('app.models.cycle_interception').CycleInterceptionReviewCommand
    assert db.query(model).count() == 2


def test_source_elo_enrichment_preserves_review_and_allows_original_auto_outcome(db, world, monkeypatch):
    facts = setup(db, world)
    process(db, world, replace(facts, players=tuple(replace(p, historical=False) for p in facts.players)))
    svc = reviewer(monkeypatch)
    for command in ('first', 'second'):
        svc.review_contribution(db, **args(db, world, command=command,
            replay_id='bfmeladder:interception-game', user_id=world[0][1].id, counted=False))
    process(db, world, facts)
    row = db.query(CycleInterceptionContribution).filter_by(user_id=world[0][1].id).one()
    assert row.calculation['historical_elo'] == '1000' and row.review_counted is False
    verify(db, world)
    assert finish(db, world, now=T + timedelta(hours=25)).outcome.value == 'exhausted'
    assert row.review_counted is False
    model = importlib.import_module('app.models.cycle_interception').CycleInterceptionReviewCommand
    assert db.query(model).count() == 2


def test_arrival_crossed_during_confirmation_rejected_before_state_write(db, world, monkeypatch):
    resolved(db, world)
    svc = reviewer(monkeypatch)
    svc.preview_outcome(db, **args(db, world, command='preview'))
    proposed = svc._proposed

    def cross_arrival(*arguments):
        result = proposed(*arguments)
        reviewer(monkeypatch, T + timedelta(hours=24))
        return result

    monkeypatch.setattr(svc, '_proposed', cross_arrival)
    with pytest.raises(ValueError, match='прибыт'):
        svc.confirm_outcome(db, **args(db, world, command='confirm', preview_command_id='preview'))
