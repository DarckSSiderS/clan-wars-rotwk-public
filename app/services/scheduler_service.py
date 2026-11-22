import asyncio
import logging
from datetime import datetime, timedelta
from time import monotonic

from sqlalchemy.orm import Session

from app.config import settings
from app.core.campaign_mode import is_interseason
from app.core.time import as_utc, utc_now
from app.database import SessionLocal
from app.models.war import ClanWar
from app.models.worker import WorkerHeartbeat
from app.services.clan_economy_service import ClanEconomyService
from app.services.ladder_service import BFMELadderService, ReplayRateLimited
from app.services.arena_match_backfill_service import ArenaMatchBackfillService
from app.services.war_service import ClanWarService
from app.services.market_service import ClanMarketService
from app.services.campaign_pause_service import CampaignPauseService
from app.services.worker_alert_service import WorkerAlertService
from app.services.cycle_runtime_service import CycleRuntimeService
from app.services.cycle_arena_ingestion_service import CycleArenaIngestionService
from app.services.cycle_administration_service import CycleAdministrationService


logger = logging.getLogger(__name__)
WORKER_NAME = "campaign"


def _utcnow() -> datetime:
    return utc_now()


class CampaignWorker:
    def __init__(self, interval_seconds: int | None = None):
        self.interval_seconds = interval_seconds or settings.SCHEDULER_UPDATE_INTERVAL
        self._stop_event = asyncio.Event()
        self._sync_requested = asyncio.Event()
        self._war_completion_lock = asyncio.Lock()
        self._replay_retry_at = None
        self._replay_rate_limits = 0
        self.alerts = WorkerAlertService()

    def _heartbeat(self, db: Session) -> WorkerHeartbeat:
        heartbeat = db.get(WorkerHeartbeat, WORKER_NAME)
        if heartbeat is None:
            heartbeat = WorkerHeartbeat(worker_name=WORKER_NAME)
            db.add(heartbeat)
        return heartbeat

    async def run_cycle(self) -> int:
        started = _utcnow()
        timer = monotonic()
        with SessionLocal() as db:
            heartbeat = self._heartbeat(db)
            if heartbeat.started_at is None:
                heartbeat.started_at = started
            heartbeat.heartbeat_at = started
            db.commit()

        try:
            with SessionLocal() as db:
                cycle_mode = CycleRuntimeService().tick(db, now=started, allow_settlement=False)
                db.commit()
            if self._replay_retry_at is not None and started < self._replay_retry_at:
                return 0
            with SessionLocal() as db:
                ladder = BFMELadderService()
                saved_count = await ladder.fetch_and_save_matches(db, limit=50)
                scan = getattr(ladder, 'last_completed_scan', None)
                interseason = is_interseason(db)
                if cycle_mode and not interseason and scan is not None:
                    CycleAdministrationService.record_complete_scan(db, scan=scan, now=_utcnow())
                # Начавшаяся до отсечки загрузка не подтверждает последующие реплеи.
                heartbeat = self._heartbeat(db)
                heartbeat.replay_synced_through_at = started
                db.commit()
                if cycle_mode and not interseason:
                    importer = CycleArenaIngestionService()
                    intake = importer.ingest_pending(db, now=_utcnow())
                    logger.info('Загрузка матчей цикла: %s ошибок источника; %s личных вкладов ожидают данных',
                        intake['source_errors'], intake['pending_receipts'])
                    if scan is not None:
                        verification = importer.verify_pending(db, scan=scan, now=_utcnow())
                        logger.info('Проверка загрузки циклов и перехватов: %s', verification)
                    CycleRuntimeService().tick(db, now=_utcnow())
                    db.commit()
                elif not CampaignPauseService.is_paused(db):
                    ClanEconomyService().settle_all(db)
                    ClanMarketService().settle_due(db)
                    ClanMarketService().expire_open_offers(db)
                elif is_interseason(db):
                    # Accepted escrow is a delivery obligation, not seasonal income.
                    ClanMarketService().settle_due(db)
            with SessionLocal() as db:
                is_paused = CampaignPauseService.is_paused(db)
            if not cycle_mode and not is_paused:
                await self._complete_due_wars()
            with SessionLocal() as db:
                completed_backfills = await ArenaMatchBackfillService().process_pending(
                    db,
                )
            with SessionLocal() as db:
                heartbeat = self._heartbeat(db)
                recovered_from_failures = int(heartbeat.consecutive_failures or 0)
                heartbeat.heartbeat_at = _utcnow()
                heartbeat.last_success_at = heartbeat.heartbeat_at
                heartbeat.last_error = None
                heartbeat.last_duration_ms = int((monotonic() - timer) * 1000)
                heartbeat.consecutive_failures = 0
                self._replay_retry_at = None
                self._replay_rate_limits = 0
                success_at = heartbeat.heartbeat_at
                db.commit()
                logger.info(
                    "Worker cycle completed: %s new matches, %s player backfills, %s ms",
                    saved_count,
                    completed_backfills,
                    heartbeat.last_duration_ms,
                )
            if recovered_from_failures:
                notification_sent = await self.alerts.notify_recovery(
                    occurred_at=success_at,
                )
                if notification_sent:
                    self._mark_notification(success_at)
            return saved_count
        except ReplayRateLimited as exc:
            now = _utcnow()
            self._replay_rate_limits += 1
            fallback = min(3600, 900 * 2 ** min(self._replay_rate_limits - 1, 2))
            delay = max(self.interval_seconds, exc.retry_after if exc.retry_after is not None else fallback)
            self._replay_retry_at = now + timedelta(seconds=delay)
            message = f'Арена ограничила загрузку реплеев (HTTP 429). Повтор не раньше {self._replay_retry_at.isoformat()}.'
            with SessionLocal() as db:
                heartbeat = self._heartbeat(db)
                heartbeat.heartbeat_at = heartbeat.last_error_at = now
                heartbeat.last_error = message
                heartbeat.last_duration_ms = int((monotonic() - timer) * 1000)
                db.commit()
            logger.warning('%s', message)
            return 0
        except Exception as exc:
            logger.exception("Campaign worker cycle failed")
            with SessionLocal() as db:
                heartbeat = self._heartbeat(db)
                heartbeat.heartbeat_at = _utcnow()
                heartbeat.last_error_at = heartbeat.heartbeat_at
                heartbeat.last_error = str(exc)[:2000]
                heartbeat.last_duration_ms = int((monotonic() - timer) * 1000)
                heartbeat.consecutive_failures = int(heartbeat.consecutive_failures or 0) + 1
                failure_count = heartbeat.consecutive_failures
                failed_at = heartbeat.heartbeat_at
                db.commit()
            notification_sent = await self.alerts.notify_failure(
                consecutive_failures=failure_count,
                occurred_at=failed_at,
            )
            if notification_sent:
                self._mark_notification(failed_at)
            raise

    def _mark_notification(self, notified_at: datetime) -> None:
        try:
            with SessionLocal() as db:
                heartbeat = self._heartbeat(db)
                heartbeat.last_notification_at = notified_at
                db.commit()
        except Exception as exc:
            logger.warning(
                "Failed to persist worker notification timestamp (%s)",
                exc.__class__.__name__,
            )

    def _next_war_end(self, db: Session) -> datetime | None:
        if CycleRuntimeService.owns_campaign(db):
            return None
        if CampaignPauseService.is_paused(db):
            return None
        return (
            db.query(ClanWar.ends_at)
            .filter(
                ClanWar.status == "active",
                ClanWar.ends_at.isnot(None),
            )
            .order_by(ClanWar.ends_at.asc())
            .limit(1)
            .scalar()
        )

    def _next_war_wake_delay(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> float:
        next_war_end = self._next_war_end(db)
        if next_war_end is None:
            return float(self.interval_seconds)

        finalization_at = as_utc(next_war_end) + timedelta(
            minutes=settings.WAR_REPLAY_GRACE_MINUTES,
        )
        seconds = (finalization_at - (as_utc(now) or _utcnow())).total_seconds()
        if seconds <= 0:
            return min(float(self.interval_seconds), 30.0)
        return min(float(self.interval_seconds), seconds)

    async def _complete_due_wars(self) -> int:
        async with self._war_completion_lock:
            with SessionLocal() as db:
                if CycleRuntimeService.owns_campaign(db):
                    return 0
                if CampaignPauseService.is_paused(db):
                    return 0
                completed = ClanWarService().complete_expired_wars(db)
            return completed

    def _request_due_replay_sync(self, db: Session, *, now: datetime | None = None) -> None:
        deadline = self._next_war_end(db)
        if deadline is None:
            return
        ready_at = as_utc(deadline) + timedelta(minutes=settings.WAR_REPLAY_GRACE_MINUTES)
        heartbeat = db.get(WorkerHeartbeat, WORKER_NAME)
        if (as_utc(now) or _utcnow()) >= ready_at and (
            not heartbeat or not heartbeat.replay_synced_through_at
            or as_utc(heartbeat.replay_synced_through_at) < ready_at
        ):
            self._sync_requested.set()

    async def _wait_or_stop(self, timeout: float, *, wake_event: asyncio.Event | None = None) -> bool:
        tasks = [asyncio.create_task(self._stop_event.wait())]
        if wake_event is not None:
            tasks.append(asyncio.create_task(wake_event.wait()))
        try:
            await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            return self._stop_event.is_set()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_sync_loop(self) -> None:
        while not self._stop_event.is_set():
            self._sync_requested.clear()
            try:
                await self.run_cycle()
            except Exception:
                pass

            if await self._wait_or_stop(float(self.interval_seconds), wake_event=self._sync_requested):
                break

    async def _run_war_deadline_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                with SessionLocal() as db:
                    delay = self._next_war_wake_delay(db)
            except Exception:
                logger.exception("Failed to calculate next war deadline")
                delay = min(float(self.interval_seconds), 30.0)

            if await self._wait_or_stop(delay):
                break

            try:
                with SessionLocal() as db:
                    self._request_due_replay_sync(db)
                completed = await self._complete_due_wars()
                if completed:
                    logger.info(
                        "War deadline timer completed %s war(s)",
                        completed,
                    )
            except Exception:
                logger.exception("War deadline timer failed")

    async def run_forever(self) -> None:
        logger.info(
            "Campaign worker started; sync interval=%s seconds, replay-aware war finalization enabled",
            self.interval_seconds,
        )
        await asyncio.gather(
            self._run_sync_loop(),
            self._run_war_deadline_loop(),
        )
        logger.info("Campaign worker stopped")

    def stop(self) -> None:
        self._stop_event.set()


class WorkerStatusService:
    def get_status(self, db: Session) -> dict:
        heartbeat = db.get(WorkerHeartbeat, WORKER_NAME)
        stale_after = timedelta(seconds=settings.SCHEDULER_UPDATE_INTERVAL * 2)
        now = _utcnow()
        is_running = bool(
            heartbeat
            and heartbeat.heartbeat_at
            and now - as_utc(heartbeat.heartbeat_at) <= stale_after
        )
        return {
            "worker_name": WORKER_NAME,
            "is_running": is_running,
            "status": "running" if is_running else "stopped",
            "interval_seconds": settings.SCHEDULER_UPDATE_INTERVAL,
            "started_at": heartbeat.started_at if heartbeat else None,
            "heartbeat_at": heartbeat.heartbeat_at if heartbeat else None,
            "last_success_at": heartbeat.last_success_at if heartbeat else None,
            "last_error_at": heartbeat.last_error_at if heartbeat else None,
            "last_error": heartbeat.last_error if heartbeat else None,
            "last_duration_ms": heartbeat.last_duration_ms if heartbeat else None,
            "consecutive_failures": int(heartbeat.consecutive_failures or 0) if heartbeat else 0,
            "last_notification_at": heartbeat.last_notification_at if heartbeat else None,
            "notifications_configured": bool(settings.WORKER_ALERT_WEBHOOK_URL),
        }
