"""Пересмотр истории не меняет подкрепление без отдельного подтверждения."""

from dataclasses import replace
from datetime import timedelta

from app.core.time import utc_now
from app.models.cycle_battle import CycleMatchContribution, CycleTerritoryBattle
from app.models.cycle_interception import (
    CycleInterception, CycleInterceptionContribution, CycleInterceptionAdjustment,
    CycleInterceptionReviewCommand,
)
from app.models.user import User
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict
from app.services.cycle_battle_service import _stored_points
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_interception_service import (
    CycleInterceptionService, applied_result, effective_counted, history_scores, PENDING,
)
from app.services.cycle_reinforcement_store import CycleReinforcementStore, encode_state, decode_state
from app.services.cycle_reinforcements import Outcome


class CycleInterceptionReviewService:
    @staticmethod
    def _text(value, maximum, label):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError(f'{label}: требуется непустая строка до {maximum} символов')
        return value.strip()

    @staticmethod
    def _locked(db, cycle_id, dispatch_id):
        cycle, aggregate, state, bindings = CycleReinforcementStore()._locked(db, cycle_id)
        dispatch = next((d for d in state.dispatches if d.id == dispatch_id), None)
        if dispatch is None or not dispatch.ambush_clan_ids:
            raise ValueError('Нет сработавшего перехвата для этой отправки')
        record = db.query(CycleInterception).filter_by(cycle_id=cycle_id,
            dispatch_id=dispatch_id).with_for_update().populate_existing().one_or_none()
        if record is None:
            raise ValueError('Сначала требуется загрузка данных перехвата')
        return cycle, aggregate, state, bindings, dispatch, record

    @staticmethod
    def _snapshot(db, record, dispatch):
        return dict(revision=record.revision, applied_result=applied_result(dispatch),
            scores={str(clan): format(score.normalize(), 'f')
                for clan, score in history_scores(db, record, dispatch).items()})

    @staticmethod
    def _bump(db, cycle, record):
        revision = record.revision
        values = {'revision': revision + 1}
        if record.verified_revision == revision:
            values['verified_revision'] = revision + 1
        changed = db.query(CycleInterception).filter_by(id=record.id, revision=revision).update(
            values, synchronize_session=False)
        if changed != 1:
            raise CycleConflict('Перехват изменился; обновите страницу')
        CampaignCycleStore._bump(db, cycle)
        db.refresh(record)

    @staticmethod
    def _remember_original(record, dispatch):
        if record.original_applied_result is None and dispatch.outcome in (Outcome.BLOCKED, Outcome.EXHAUSTED):
            record.original_applied_result = applied_result(dispatch)

    def _execute(self, db, *, cycle_id, dispatch_id, command_id, expected_revision,
                 actor_user_id, reason, action, payload, apply):
        command_id = self._text(command_id, 120, 'Идентификатор команды')
        reason = self._text(reason, 500, 'Причина')
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError('Требуется актуальная версия перехвата')
        if type(actor_user_id) is not int or actor_user_id < 1 or db.get(User, actor_user_id) is None:
            raise ValueError('Неизвестный администратор')
        with CycleEconomyStore._atomic(db):
            context = self._locked(db, cycle_id, dispatch_id)
            cycle, _, _, _, dispatch, record = context
            old = db.query(CycleInterceptionReviewCommand).filter_by(
                interception_id=record.id, command_id=command_id).one_or_none()
            if old is not None:
                if (old.action, old.actor_user_id, old.reason, old.expected_revision, old.payload) != (
                        action, actor_user_id, reason, expected_revision, payload):
                    raise ValueError('Идентификатор команды уже использован с другими параметрами')
                return old.result
            if record.revision != expected_revision:
                raise CycleConflict('Версия перехвата изменилась; обновите страницу')
            now = utc_now()
            before = self._snapshot(db, record, dispatch)
            result, updated_dispatch = apply(*context, now, reason, command_id)
            if action != 'preview_outcome':
                self._bump(db, cycle, record)
            after = self._snapshot(db, record, updated_dispatch)
            result = {**result, 'revision': record.revision}
            db.add(CycleInterceptionReviewCommand(interception_id=record.id, command_id=command_id,
                action=action, actor_user_id=actor_user_id, reason=reason, expected_revision=expected_revision,
                payload=payload, before=before, after=after, result=result, created_at=now))
            db.flush()
            return result

    def review_contribution(self, db, *, replay_id, user_id, counted, **command):
        replay_id = self._text(replay_id, 120, 'Идентификатор реплея')
        if type(user_id) is not int or user_id < 1 or type(counted) is not bool:
            raise ValueError('Требуются идентификатор игрока и решение о зачёте')

        def apply(cycle, aggregate, state, bindings, dispatch, record, now, reason, command_id):
            row = db.query(CycleInterceptionContribution).filter_by(interception_id=record.id,
                replay_id=replay_id, user_id=user_id).one_or_none()
            sides = {p: dispatch.sender_clan_id for p in dispatch.players}
            sides.update({p: a.clan_id for a in state.ambushes if a.dispatch_id == dispatch.id for p in a.players})
            if row is None or user_id not in bindings or sides.get(bindings[user_id][1]) != row.side_clan_id:
                raise ValueError('Нет вклада с зафиксированной привязкой игрока к стороне перехвата')
            if (row.calculation.get('source'), row.calculation.get('uuid')) != (
                    bindings[user_id][1].source, str(bindings[user_id][1].uuid)):
                raise ValueError('UUID вклада не совпадает с зафиксированной привязкой')
            if counted and (row.reason in PENDING or row.calculation.get('historical_elo') is None):
                raise ValueError('Нет подтверждённого исторического Elo; используйте отдельную ручную поправку')
            if counted and row.reason != 'counted':
                raise ValueError('Вклад исключён проверкой источника; используйте отдельную ручную поправку')
            before = effective_counted(row)
            self._remember_original(record, dispatch)
            row.review_counted = counted
            db.flush()
            return dict(replay_id=replay_id, user_id=user_id, counted=counted, previous_counted=before), dispatch

        return self._execute(db, action='review', payload=dict(replay_id=replay_id, user_id=user_id,
            counted=counted), apply=apply, **command)

    def adjust(self, db, *, side_clan_id, amount, **command):
        amount = _stored_points(amount)
        if type(side_clan_id) is not int or side_clan_id < 1:
            raise ValueError('Требуется идентификатор стороны перехвата')

        def apply(cycle, aggregate, state, bindings, dispatch, record, now, reason, command_id):
            if side_clan_id not in (dispatch.sender_clan_id, *dispatch.ambush_clan_ids):
                raise ValueError('Клан не является стороной перехвата')
            self._remember_original(record, dispatch)
            row = CycleInterceptionAdjustment(interception_id=record.id, command_id=command_id,
                side_clan_id=side_clan_id, points=amount, reason=reason,
                actor_user_id=command['actor_user_id'], created_at=now)
            db.add(row)
            db.flush()
            return dict(adjustment_id=row.id, side_clan_id=side_clan_id, points=str(amount)), dispatch

        return self._execute(db, action='adjust', payload=dict(side_clan_id=side_clan_id,
            amount=str(amount)), apply=apply, **command)

    @staticmethod
    def _can_apply(db, cycle, record, dispatch, now):
        if now >= dispatch.arrives_at:
            raise ValueError('После фактического прибытия изменение исхода запрещено')
        if cycle.settled_at is not None:
            raise ValueError('Цикл уже завершён; разрешено только исправление истории счёта')
        if now < dispatch.interception_ends_at + timedelta(minutes=5):
            raise ValueError('Приём последних реплеев ещё не завершён')
        if CycleInterceptionService._pending_sources(cycle):
            raise ValueError('Сначала требуется разрешить привязки реплеев источника')
        if record.completed_at is None and (record.verified_at is None or record.verified_revision != record.revision):
            raise ValueError('Сначала требуется полная проверка окна перехвата')

    @staticmethod
    def _proposed(db, record, dispatch):
        scores = history_scores(db, record, dispatch)
        help_score = scores[dispatch.sender_clan_id]
        blocked = any(scores[clan] > 0 and scores[clan] > help_score for clan in dispatch.ambush_clan_ids)
        return replace(dispatch, help_score=help_score,
            ambush_scores=tuple((clan, scores[clan]) for clan in dispatch.ambush_clan_ids),
            outcome=Outcome.BLOCKED if blocked else Outcome.EXHAUSTED)

    def preview_outcome(self, db, **command):
        def apply(cycle, aggregate, state, bindings, dispatch, record, now, reason, command_id):
            self._can_apply(db, cycle, record, dispatch, now)
            proposed = self._proposed(db, record, dispatch)
            return dict(preview_command_id=command_id, aggregate_revision=aggregate.revision,
                applied_result=applied_result(dispatch), proposed_result=applied_result(proposed),
                arrives_at=dispatch.arrives_at.isoformat()), dispatch

        return self._execute(db, action='preview_outcome', payload={}, apply=apply, **command)

    def confirm_outcome(self, db, *, preview_command_id, **command):
        preview_command_id = self._text(preview_command_id, 120, 'Идентификатор предпросмотра')

        def apply(cycle, aggregate, state, bindings, dispatch, record, now, reason, command_id):
            self._can_apply(db, cycle, record, dispatch, now)
            preview = db.query(CycleInterceptionReviewCommand).filter_by(interception_id=record.id,
                command_id=preview_command_id, action='preview_outcome').one_or_none()
            if (preview is None or preview.actor_user_id != command['actor_user_id']
                    or preview.expected_revision != record.revision
                    or preview.result['aggregate_revision'] != aggregate.revision):
                raise CycleConflict('Предпросмотр отсутствует или данные изменились; повторите предпросмотр')
            proposed = self._proposed(db, record, dispatch)
            if preview.result['proposed_result'] != applied_result(proposed):
                raise CycleConflict('Счёт изменился; повторите предпросмотр')
            helpers = [uid for uid, (_, identity) in bindings.items() if identity in dispatch.players]
            if db.query(CycleMatchContribution.id).join(CycleTerritoryBattle,
                    CycleMatchContribution.battle_id == CycleTerritoryBattle.id).filter(
                    CycleTerritoryBattle.cycle_id == cycle.id,
                    CycleTerritoryBattle.territory_id == dispatch.territory_id,
                    CycleMatchContribution.user_id.in_(helpers), CycleMatchContribution.counted.is_(True),
                    CycleMatchContribution.points != 0).first():
                raise ValueError('Обнаружены территориальные очки подкрепления до прибытия; изменение запрещено')
            updated = replace(state, dispatches=tuple(proposed if d.id == dispatch.id else d for d in state.dispatches))
            if decode_state(encode_state(updated)) != updated:
                raise ValueError('Нарушена структура состояния подкреплений')
            now = utc_now()
            self._can_apply(db, cycle, record, dispatch, now)
            self._remember_original(record, dispatch)
            CycleReinforcementStore()._write(db, cycle, aggregate, updated, aggregate.revision)
            if record.completed_at is None:
                record.completed_at = now
                record.original_applied_result = applied_result(proposed)
                key = f'interception:{dispatch.id}'
                if key not in cycle.dependencies:
                    raise ValueError('Нет зависимости завершения перехвата')
                CampaignCycleStore().complete_dependency(db, cycle_id=cycle.id, key=key)
            db.flush()
            return dict(applied_result=applied_result(proposed),
                original_applied_result=record.original_applied_result), proposed

        return self._execute(db, action='confirm_outcome', payload=dict(preview_command_id=preview_command_id),
            apply=apply, **command)

    def read(self, db, *, cycle_id, dispatch_id):
        result = CycleInterceptionService().read(db, cycle_id=cycle_id, dispatch_id=dispatch_id, now=utc_now())
        record = db.query(CycleInterception).filter_by(cycle_id=cycle_id, dispatch_id=dispatch_id).one_or_none()
        result['audit'] = [dict(command_id=row.command_id, action=row.action, actor_user_id=row.actor_user_id,
            reason=row.reason, expected_revision=row.expected_revision, before=row.before, after=row.after,
            created_at=row.created_at) for row in db.query(CycleInterceptionReviewCommand).filter_by(
                interception_id=record.id).order_by(CycleInterceptionReviewCommand.id)] if record else []
        return result
