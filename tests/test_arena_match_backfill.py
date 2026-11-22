from datetime import timedelta

import pytest

from app.core.time import as_utc, utc_now
from app.models.arena_match_backfill import ArenaMatchBackfillJob
from app.models.external_identity import ExternalPlayerAlias, ExternalPlayerIdentity
from app.models.user import User
from app.services.arena_match_backfill_service import ArenaMatchBackfillService


def _arena_user(db, nickname="ArenaPlayer"):
    now = utc_now()
    user = User(
        username=nickname,
        display_name=nickname,
        is_active=True,
        is_claimed=True,
    )
    identity = ExternalPlayerIdentity(
        user=user,
        source="bfmeladder",
        external_uuid=f"uuid-{nickname}",
        current_nickname=nickname,
        verification_status="verified",
        claimed_at=now,
        verified_at=now,
        first_seen_at=now,
        last_seen_at=now,
    )
    identity.aliases.append(
        ExternalPlayerAlias(
            nickname=nickname,
            first_seen_at=now,
            last_seen_at=now,
        )
    )
    db.add(user)
    db.commit()
    return user


def test_queue_is_idempotent_for_repeated_arena_logins(db):
    user = _arena_user(db)
    service = ArenaMatchBackfillService()

    first, first_should_dispatch = service.ensure_queued(db, user)
    db.commit()
    second, second_should_dispatch = service.ensure_queued(db, user)

    assert first_should_dispatch is True
    assert second_should_dispatch is True
    assert first.id == second.id
    assert db.query(ArenaMatchBackfillJob).count() == 1

    first.status = "completed"
    first.completed_at = utc_now()
    db.commit()
    completed, completed_should_dispatch = service.ensure_queued(db, user)

    assert completed.id == first.id
    assert completed_should_dispatch is False
    assert db.query(ArenaMatchBackfillJob).count() == 1


@pytest.mark.asyncio
async def test_job_imports_current_arena_nickname_and_records_counts(db):
    user = _arena_user(db, "CurrentArenaNick")
    requested_nicknames = []

    class SuccessfulLadder:
        last_scanned_count = 0

        async def fetch_and_save_player_history(self, session, nickname):
            assert session is db
            requested_nicknames.append(nickname)
            self.last_scanned_count = 17
            return 9

    service = ArenaMatchBackfillService(ladder_factory=SuccessfulLadder)
    job, _ = service.ensure_queued(db, user)
    db.commit()

    completed = await service.process_job(db, job.id)

    db.refresh(job)
    assert completed is True
    assert requested_nicknames == ["CurrentArenaNick"]
    assert job.status == "completed"
    assert job.attempts == 1
    assert job.scanned_count == 17
    assert job.imported_count == 9
    assert job.completed_at is not None
    assert job.last_error is None


@pytest.mark.asyncio
async def test_failed_arena_import_is_retried_without_raising(db, monkeypatch):
    user = _arena_user(db, "RetryPlayer")

    class FailingLadder:
        last_scanned_count = 0

        async def fetch_and_save_player_history(self, session, nickname):
            raise RuntimeError("temporary archive failure")

    monkeypatch.setattr(
        "app.services.arena_match_backfill_service.settings.ARENA_BACKFILL_RETRY_SECONDS",
        90,
    )
    service = ArenaMatchBackfillService(ladder_factory=FailingLadder)
    job, _ = service.ensure_queued(db, user)
    db.commit()
    before = utc_now()

    completed = await service.process_job(db, job.id)

    db.refresh(job)
    assert completed is False
    assert job.status == "failed"
    assert job.attempts == 1
    assert "temporary archive failure" in job.last_error
    assert as_utc(job.next_attempt_at) >= before + timedelta(seconds=90)
    assert await service.process_job(db, job.id) is False
    db.refresh(job)
    assert job.attempts == 1
