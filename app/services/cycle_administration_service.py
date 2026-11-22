"""Явные восстановительные действия; не управляет остановкой сезонов."""

import hashlib

from sqlalchemy import func

from app.core.time import as_utc
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCyclePlan, CampaignCycleRecord, CycleScoutRequest
from app.models.cycle_arena_scan import CycleArenaScanState
from app.models.cycle_battle import CycleMatchContribution, CycleTerritoryBattle
from app.models.cycle_economy import CycleEconomySnapshot
from app.models.cycle_interception import CycleInterceptionContribution, CycleInterception
from app.models.cycle_reinforcement_state import CycleReinforcementState
from app.models.cycle_startup import CycleStartup
from app.models.operation import AdminAuditLog
from app.models.worker import WorkerHeartbeat
from app.services.arena_replay_scan import ArenaReplayScan
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_plan_service import CyclePlanService
from app.services.cycle_startup_service import CycleStartupService
from app.services.operation_service import AdminAuditService


PENDING_REASONS = ('missing_historical_elo', 'missing_match_times', 'unknown_result', 'interception_pending')


class CycleAdministrationService:
    @staticmethod
    def recovery_available(db, cycle, now):
        season = db.get(CampaignSeason, cycle.season_id)
        if (season is None or season.status != 'active'
                or (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1'
                or cycle.planning_snapshot is not None or cycle.orders_frozen_at is not None
                or cycle.battles_registered or cycle.settled_at is not None
                or cycle.import_verified_at is not None or cycle.dependencies
                or as_utc(now) < CampaignCycleStore.timeline(cycle).battle_at
                or db.get(CycleStartup, cycle.season_id) is None):
            return False
        if db.query(CampaignCycleRecord.id).filter(CampaignCycleRecord.season_id == cycle.season_id,
                CampaignCycleRecord.number > cycle.number).first():
            return False
        for model in (CampaignCyclePlan, CycleScoutRequest, CycleTerritoryBattle,
                      CycleEconomySnapshot, CycleReinforcementState):
            if db.query(model).filter_by(cycle_id=cycle.id).first():
                return False
        return True

    def recover_preparation(self, db, *, cycle_id, actor_user_id, expected_revision, command_id, reason, now):
        now = as_utc(now)
        reason = reason.strip()
        if not 3 <= len(reason) <= 500 or not isinstance(command_id, str) or not 1 <= len(command_id.strip()) <= 120:
            raise ValueError('Укажите причину восстановления и идентификатор команды')
        key = hashlib.sha256(f'{cycle_id}:{command_id}'.encode()).hexdigest()
        with CycleEconomyStore._atomic(db):
            cycle = CampaignCycleStore()._locked(db, cycle_id)
            receipt = db.query(AdminAuditLog).filter_by(action='cycle_preparation_recovered',
                entity_type='cycle_recovery_command', entity_id=key).one_or_none()
            if receipt:
                if receipt.actor_user_id != actor_user_id or receipt.reason != reason:
                    raise ValueError('Этот идентификатор уже использован для другого восстановления')
                return dict(receipt.after_data)
            if cycle.revision != expected_revision:
                raise CycleConflict('Цикл изменился; обновите данные перед восстановлением')
            if not self.recovery_available(db, cycle, now):
                raise ValueError('Восстановление доступно только для пропущенной подготовки без снимков и битв')
            before = dict(preparation_at=as_utc(cycle.preparation_at).isoformat(), revision=cycle.revision)
            # Закрыть первоначальное окно подарков до переноса подготовки.
            startup = db.get(CycleStartup, cycle.season_id)
            if startup.expired_at is None:
                CycleStartupService().expire(db, cycle_id=cycle.id, now=now)
            cycle.preparation_at = now
            db.flush()
            CampaignCycleStore._bump(db, cycle)
            CyclePlanService().capture_preparation(db, cycle_id=cycle.id, now=now)
            result = dict(cycle_id=cycle.id, revision=cycle.revision,
                preparation_at=now.isoformat(), battle_at=CampaignCycleStore.timeline(cycle).battle_at.isoformat())
            AdminAuditService().record(db, actor_user_id=actor_user_id,
                action='cycle_preparation_recovered', entity_type='cycle_recovery_command', entity_id=key,
                before_data=before, after_data=result, reason=reason)
            db.flush()
            return result

    @staticmethod
    def record_complete_scan(db, *, scan, now):
        now = as_utc(now)
        if not isinstance(scan, ArenaReplayScan) or scan.covered_end > now:
            raise ValueError('Нужно подтверждение полностью сохранённого обхода Арены')
        row = db.query(CycleArenaScanState).filter_by(source='bfmeladder').with_for_update().populate_existing().one_or_none()
        if row is not None and as_utc(row.covered_end) > scan.covered_end:
            return row
        if row is None:
            row = CycleArenaScanState(source='bfmeladder')
            db.add(row)
        row.covered_start, row.covered_end = scan.covered_start, scan.covered_end
        row.completed_at, row.replays_count = now, len(scan.replay_ids)
        db.flush()
        return row

    def diagnostics(self, db, *, now):
        now = as_utc(now)
        season = db.query(CampaignSeason).filter_by(status='active').order_by(CampaignSeason.number.desc()).first()
        mode = (season.rules_snapshot or {}).get('mechanics_version', 'legacy') if season else 'legacy'
        cycle = db.query(CampaignCycleRecord).filter_by(season_id=season.id).order_by(
            CampaignCycleRecord.number.desc()).first() if season and mode == 'cycle_v1' else None
        heartbeat = db.get(WorkerHeartbeat, 'campaign')
        scan = db.get(CycleArenaScanState, 'bfmeladder')
        result = dict(server_time=now, mechanics_version=mode, season_id=season.id if season else None, cycle=None,
            arena=dict(last_complete_scan=dict(completed_at=as_utc(scan.completed_at),
                covered_start=as_utc(scan.covered_start), covered_end=as_utc(scan.covered_end),
                replays_count=scan.replays_count) if scan else None,
                heartbeat_at=as_utc(heartbeat.heartbeat_at) if heartbeat else None,
                last_worker_success_at=as_utc(heartbeat.last_success_at) if heartbeat else None,
                worker_failures=int(heartbeat.consecutive_failures or 0) if heartbeat else 0,
                pending_contributions=[], pending_source_replays=0, pending_interceptions=0))
        if cycle is None:
            return result
        timeline = CampaignCycleStore.timeline(cycle)
        result['cycle'] = dict(id=cycle.id, number=cycle.number, revision=cycle.revision,
            phase=timeline.phase_at(now).value if now >= timeline.starts_at else 'scheduled',
            preparation_at=timeline.preparation_at, battle_at=timeline.battle_at,
            battle_ends_at=timeline.battle_ends_at, replay_deadline=timeline.replay_deadline,
            settled_at=as_utc(cycle.settled_at), import_verified_at=as_utc(cycle.import_verified_at),
            recovery_available=self.recovery_available(db, cycle, now))
        counts = dict(db.query(CycleMatchContribution.reason, func.count(CycleMatchContribution.id)).join(
            CycleTerritoryBattle).filter(CycleTerritoryBattle.cycle_id == cycle.id,
                CycleMatchContribution.review_reason.is_(None),
                CycleMatchContribution.reason.in_(PENDING_REASONS)).group_by(CycleMatchContribution.reason).all())
        for reason, count in db.query(CycleInterceptionContribution.reason,
                func.count(CycleInterceptionContribution.id)).join(CycleInterception).filter(
                    CycleInterception.cycle_id == cycle.id, CycleInterceptionContribution.review_counted.is_(None),
                    CycleInterceptionContribution.reason.in_(PENDING_REASONS)).group_by(CycleInterceptionContribution.reason):
            counts[reason] = counts.get(reason, 0) + count
        result['arena']['pending_contributions'] = [dict(reason=reason, count=count) for reason, count in sorted(counts.items())]
        for key, done in (cycle.dependencies or {}).items():
            if not done and key.startswith('source-replay:'):
                result['arena']['pending_source_replays'] += 1
            if not done and key.startswith('interception:'):
                result['arena']['pending_interceptions'] += 1
        return result
