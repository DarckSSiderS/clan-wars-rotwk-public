import logging
from datetime import timedelta
from typing import Callable

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.time import as_utc, utc_now
from app.database import SessionLocal
from app.models.arena_match_backfill import ArenaMatchBackfillJob
from app.models.external_identity import ExternalPlayerIdentity
from app.models.user import User
from app.services.ladder_service import BFMELadderService


logger = logging.getLogger(__name__)


class ArenaMatchBackfillService:
    SOURCE = "bfmeladder"
    STALE_AFTER = timedelta(minutes=30)

    def __init__(
        self,
        ladder_factory: Callable[[], BFMELadderService] = BFMELadderService,
    ) -> None:
        self.ladder_factory = ladder_factory

    def ensure_queued(
        self,
        db: Session,
        user: User,
    ) -> tuple[ArenaMatchBackfillJob, bool]:
        identity = (
            db.query(ExternalPlayerIdentity)
            .filter(
                ExternalPlayerIdentity.user_id == user.id,
                ExternalPlayerIdentity.source == self.SOURCE,
                ExternalPlayerIdentity.verification_status == "verified",
            )
            .one_or_none()
        )
        if identity is None:
            raise ValueError("Verified BFME Arena identity is required")

        existing = (
            db.query(ArenaMatchBackfillJob)
            .filter(ArenaMatchBackfillJob.identity_id == identity.id)
            .one_or_none()
        )
        if existing is not None:
            return existing, self._is_ready(existing)

        now = utc_now()
        job = ArenaMatchBackfillJob(
            identity_id=identity.id,
            status="pending",
            attempts=0,
            next_attempt_at=now,
            requested_at=now,
        )
        try:
            with db.begin_nested():
                db.add(job)
                db.flush()
        except IntegrityError:
            existing = (
                db.query(ArenaMatchBackfillJob)
                .filter(ArenaMatchBackfillJob.identity_id == identity.id)
                .one_or_none()
            )
            if existing is None:
                raise
            return existing, self._is_ready(existing)
        return job, True

    async def process_job(self, db: Session, job_id: int) -> bool:
        job = self._claim(db, job_id)
        if job is None:
            return False
        nickname = job.identity.current_nickname
        ladder = self.ladder_factory()
        try:
            imported_count = await ladder.fetch_and_save_player_history(
                db,
                nickname,
            )
        except Exception as exc:
            db.rollback()
            failed_job = db.get(ArenaMatchBackfillJob, job_id)
            if failed_job is not None:
                failed_job.status = "failed"
                failed_job.completed_at = None
                failed_job.last_error = f"{type(exc).__name__}: {str(exc)}"[:2000]
                failed_job.next_attempt_at = utc_now() + self._retry_delay(
                    failed_job.attempts,
                )
                db.commit()
            logger.exception(
                "BFME Arena player match backfill failed for job %s",
                job_id,
            )
            return False

        completed_job = db.get(ArenaMatchBackfillJob, job_id)
        if completed_job is None:
            return False
        completed_job.status = "completed"
        completed_job.completed_at = utc_now()
        completed_job.next_attempt_at = completed_job.completed_at
        completed_job.last_error = None
        completed_job.scanned_count = int(ladder.last_scanned_count or 0)
        completed_job.imported_count = int(imported_count or 0)
        db.commit()
        logger.info(
            "BFME Arena player match backfill completed for job %s: "
            "scanned=%s imported=%s",
            job_id,
            completed_job.scanned_count,
            completed_job.imported_count,
        )
        return True

    async def process_job_by_id(self, job_id: int) -> bool:
        with SessionLocal() as db:
            return await self.process_job(db, job_id)

    async def process_pending(
        self,
        db: Session,
        limit: int | None = None,
    ) -> int:
        now = utc_now()
        stale_before = now - self.STALE_AFTER
        job_ids = [
            job_id
            for (job_id,) in (
                db.query(ArenaMatchBackfillJob.id)
                .filter(self._ready_filter(now, stale_before))
                .order_by(
                    ArenaMatchBackfillJob.next_attempt_at,
                    ArenaMatchBackfillJob.id,
                )
                .limit(
                    settings.ARENA_BACKFILL_JOBS_PER_CYCLE
                    if limit is None
                    else max(0, limit)
                )
                .all()
            )
        ]
        completed = 0
        for job_id in job_ids:
            if await self.process_job(db, job_id):
                completed += 1
        return completed

    def _claim(
        self,
        db: Session,
        job_id: int,
    ) -> ArenaMatchBackfillJob | None:
        now = utc_now()
        job = (
            db.query(ArenaMatchBackfillJob)
            .filter(
                ArenaMatchBackfillJob.id == job_id,
                self._ready_filter(now, now - self.STALE_AFTER),
            )
            .with_for_update(skip_locked=True)
            .one_or_none()
        )
        if job is None:
            return None
        job.status = "running"
        job.started_at = now
        job.completed_at = None
        job.last_error = None
        job.attempts = int(job.attempts or 0) + 1
        db.commit()
        db.refresh(job)
        return job

    @classmethod
    def _ready_filter(cls, now, stale_before):
        return or_(
            and_(
                ArenaMatchBackfillJob.status.in_(("pending", "failed")),
                ArenaMatchBackfillJob.next_attempt_at <= now,
            ),
            and_(
                ArenaMatchBackfillJob.status == "running",
                ArenaMatchBackfillJob.started_at <= stale_before,
            ),
        )

    @classmethod
    def _is_ready(cls, job: ArenaMatchBackfillJob) -> bool:
        now = utc_now()
        next_attempt_at = as_utc(job.next_attempt_at)
        started_at = as_utc(job.started_at)
        if job.status in {"pending", "failed"}:
            return next_attempt_at is None or next_attempt_at <= now
        return bool(
            job.status == "running"
            and started_at is not None
            and started_at <= now - cls.STALE_AFTER
        )

    @staticmethod
    def _retry_delay(attempts: int) -> timedelta:
        exponent = min(max(int(attempts or 1) - 1, 0), 6)
        seconds = min(
            3600,
            settings.ARENA_BACKFILL_RETRY_SECONDS * (2**exponent),
        )
        return timedelta(seconds=seconds)
