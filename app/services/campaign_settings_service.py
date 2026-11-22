from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.campaign import CampaignSettings, ReplaySyncState
from app.services.elo_service import PATCH_202, PATCH_ENNORATH


SYNC_STATUSES = {"imported", "known", "skipped", "error"}


class CampaignSettingsService:
    SETTINGS_ID = 1

    def get_or_create(self, db: Session) -> CampaignSettings:
        campaign = db.get(CampaignSettings, self.SETTINGS_ID)
        if campaign is None:
            campaign = CampaignSettings(
                id=self.SETTINGS_ID,
                patch_202_enabled=True,
                ennorath_enabled=True,
            )
            db.add(campaign)
            db.commit()
            db.refresh(campaign)
        return campaign

    def active_patch_families(self, db: Session) -> set[str]:
        campaign = self.get_or_create(db)
        active = set()
        if campaign.patch_202_enabled:
            active.add(PATCH_202)
        if campaign.ennorath_enabled:
            active.add(PATCH_ENNORATH)
        return active

    def update(
        self,
        db: Session,
        *,
        patch_202_enabled: bool,
        ennorath_enabled: bool,
        updated_by: str,
    ) -> CampaignSettings:
        if not patch_202_enabled and not ennorath_enabled:
            raise ValueError("Должен быть активен хотя бы один патч сезона")
        campaign = self.get_or_create(db)
        campaign.patch_202_enabled = patch_202_enabled
        campaign.ennorath_enabled = ennorath_enabled
        campaign.updated_by = updated_by
        db.commit()
        db.refresh(campaign)
        return campaign


class ReplaySyncStateService:
    def record(
        self,
        db: Session,
        replay_id: str,
        status: str,
        *,
        patch_family: str | None = None,
        patch_name: str | None = None,
        reason: str | None = None,
        commit: bool = False,
    ) -> ReplaySyncState:
        if status not in SYNC_STATUSES:
            raise ValueError(f"Неизвестный статус replay: {status}")
        now = utc_now()
        state = db.get(ReplaySyncState, str(replay_id))
        if state is None:
            state = ReplaySyncState(
                replay_id=str(replay_id),
                status=status,
                patch_family=patch_family,
                patch_name=patch_name,
                reason=reason,
                attempts=1,
                first_seen_at=now,
                last_attempt_at=now,
            )
            db.add(state)
        else:
            next_status = (
                "imported"
                if state.status == "imported" and status == "known"
                else status
            )
            state.status = next_status
            state.patch_family = patch_family or state.patch_family
            state.patch_name = patch_name or state.patch_name
            state.reason = reason
            state.attempts = int(state.attempts or 0) + 1
            state.last_attempt_at = now
        if state.status in {"imported", "known"}:
            state.imported_at = state.imported_at or now
            state.reason = None
        if commit:
            db.commit()
            db.refresh(state)
        else:
            db.flush()
        return state

    def summary(self, db: Session) -> dict:
        counts = dict(
            db.query(ReplaySyncState.status, func.count(ReplaySyncState.replay_id))
            .group_by(ReplaySyncState.status)
            .all()
        )
        return {
            status: int(counts.get(status, 0))
            for status in ("imported", "known", "skipped", "error")
        }

    def list_states(
        self,
        db: Session,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ReplaySyncState]:
        query = db.query(ReplaySyncState)
        if status:
            query = query.filter(ReplaySyncState.status == status)
        return (
            query.order_by(ReplaySyncState.last_attempt_at.desc())
            .limit(max(1, min(limit, 500)))
            .all()
        )
