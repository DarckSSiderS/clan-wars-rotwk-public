"""Transactional storage for opt-in cycle seasons; never commits caller work."""

from datetime import datetime
from dataclasses import replace

from sqlalchemy.orm import Session

from app.core.time import as_utc
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.cycle_battle import CycleMatchContribution, CycleTerritoryBattle
from app.services.campaign_cycle_service import CampaignCycle, CyclePhase, _utc


class CycleConflict(ValueError):
    pass


class CampaignCycleStore:
    @staticmethod
    def timeline(row: CampaignCycleRecord) -> CampaignCycle:
        return CampaignCycle(
            season_id=row.season_id, rule_version=row.rule_version,
            number=row.number, starts_at=as_utc(row.starts_at),
            preparation_at=as_utc(row.preparation_at),
            settled_at=as_utc(row.settled_at) if row.settled_at else None,
            season_end_requested=row.season_end_requested,
        )

    def _locked(self, db, cycle_id, expected_revision=None):
        row = db.query(CampaignCycleRecord).filter_by(id=cycle_id).with_for_update().populate_existing().one_or_none()
        if row is None:
            raise ValueError('Unknown cycle')
        if expected_revision is not None and row.revision != expected_revision:
            raise CycleConflict('Cycle revision changed; refresh before retry')
        return row

    @staticmethod
    def _bump(db, row):
        revision = row.revision
        changed = db.query(CampaignCycleRecord).filter_by(id=row.id, revision=revision).update(
            {'revision': revision + 1}, synchronize_session=False,
        )
        if changed != 1:
            raise CycleConflict('Concurrent cycle update')
        db.refresh(row)

    @staticmethod
    def _insert(db, timeline):
        row = CampaignCycleRecord(
            season_id=timeline.season_id, number=timeline.number,
            rule_version=timeline.rule_version, starts_at=timeline.starts_at,
            preparation_at=timeline.preparation_at, dependencies={},
        )
        db.add(row)
        db.flush()
        return row

    def start(self, db: Session, *, season_id: int):
        season = db.query(CampaignSeason).filter_by(id=season_id).with_for_update().one_or_none()
        if season is None or season.status != 'active':
            raise ValueError('An active season is required')
        snapshot = season.rules_snapshot or {}
        if snapshot.get('mechanics_version') != 'cycle_v1':
            raise ValueError('Season must explicitly enable cycle_v1')
        existing = db.query(CampaignCycleRecord).filter_by(season_id=season_id, number=1).one_or_none()
        if existing:
            return existing
        return self._insert(db, CampaignCycle.first(
            season_id=season_id, rule_version=snapshot.get('version'),
            starts_at=as_utc(season.starts_at),
        ))

    def register_dependency(self, db, *, cycle_id, key):
        row = self._locked(db, cycle_id)
        if row.settled_at is not None:
            raise ValueError('Settled cycle dependencies are immutable')
        if not isinstance(key, str) or not key.strip():
            raise ValueError('Dependency key is required')
        if key not in row.dependencies:
            self._bump(db, row)
            row.dependencies = {**row.dependencies, key: False}
            db.flush()
        return row

    def complete_dependency(self, db, *, cycle_id, key):
        row = self._locked(db, cycle_id)
        if key not in row.dependencies:
            raise ValueError('Unknown dependency')
        if not row.dependencies[key]:
            if row.settled_at is not None:
                raise ValueError('Settled cycle dependencies are immutable')
            self._bump(db, row)
            row.dependencies = {**row.dependencies, key: True}
            db.flush()
        return row

    def mark_import_complete(self, db, *, cycle_id, verified_at: datetime):
        row = self._locked(db, cycle_id)
        verified_at = _utc(verified_at)
        if verified_at < self.timeline(row).replay_deadline:
            raise ValueError('Full import window must have ended')
        if any(not done for key, done in row.dependencies.items() if key.startswith('source-replay:')):
            raise ValueError('Pending source replay identities must be resolved before import verification')
        pending = db.query(CycleMatchContribution.id).join(CycleTerritoryBattle).filter(
            CycleTerritoryBattle.cycle_id == cycle_id,
            CycleMatchContribution.review_reason.is_(None),
            CycleMatchContribution.reason.in_(('missing_historical_elo', 'missing_match_times',
                'unknown_result', 'interception_pending'))).first()
        if pending is not None:
            raise ValueError('Pending personal replay evidence must be resolved before import verification')
        if row.import_verified_at is None:
            self._bump(db, row)
            row.import_verified_at = verified_at
            db.flush()
        return row

    def settle(self, db, *, cycle_id, completed_at: datetime):
        row = self._locked(db, cycle_id)
        if row.settled_at is not None:
            return row
        completed_at = _utc(completed_at)
        if row.import_verified_at is None or completed_at < as_utc(row.import_verified_at):
            raise ValueError('Successful import verification is required')
        if row.orders_frozen_at is None or not row.battles_registered:
            raise ValueError('Frozen orders and complete battle creation are required')
        if not all(row.dependencies.values()):
            raise ValueError('Unfinished dependencies')
        settled = self.timeline(row).settle(completed_at)
        self._bump(db, row)
        row.settled_at = settled.settled_at
        db.flush()
        return row

    def request_end(self, db, *, cycle_id, expected_revision=None):
        row = self._locked(db, cycle_id, expected_revision)
        if not row.season_end_requested:
            if db.query(CampaignCycleRecord.id).filter_by(season_id=row.season_id, number=row.number + 1).first():
                raise ValueError('End must be requested on the latest cycle')
            self._bump(db, row)
            row.season_end_requested = True
            db.flush()
        return row

    def advance(self, db, *, cycle_id, now: datetime, rule_version: int):
        row = self._locked(db, cycle_id)
        timeline = self.timeline(row)
        if timeline.phase_at(now) != CyclePhase.COMPLETE:
            raise ValueError('Full settlement and rest are required')
        season = db.query(CampaignSeason).filter_by(id=row.season_id).with_for_update().one()
        if season.status != 'active':
            raise ValueError('Season is no longer active')
        following = db.query(CampaignCycleRecord).filter_by(season_id=row.season_id, number=row.number + 1).one_or_none()
        if following:
            return following
        following_timeline = timeline.next_cycle(rule_version=rule_version)
        # A stopped worker cannot retroactively give clans a planning window.
        preparation_at = max(following_timeline.preparation_at, _utc(now))
        return self._insert(db, replace(following_timeline, starts_at=preparation_at,
                                        preparation_at=preparation_at))
