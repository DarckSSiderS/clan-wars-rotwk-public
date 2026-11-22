"""New-season time rules, deliberately independent of the live scheduler."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware datetime required")
    return value.astimezone(timezone.utc)


class CyclePhase(str, Enum):
    REGISTRATION = "registration"
    PREPARATION = "preparation"
    BATTLE = "battle"
    REPLAY_LOADING = "replay_loading"
    SETTLEMENT = "settlement"
    REST = "rest"
    COMPLETE = "complete"
    SEASON_ENDED = "season_ended"


@dataclass(frozen=True)
class CampaignCycle:
    season_id: int
    rule_version: int
    number: int
    starts_at: datetime
    preparation_at: datetime
    settled_at: datetime | None = None
    season_end_requested: bool = False

    def __post_init__(self):
        for value in (self.season_id, self.rule_version, self.number):
            if type(value) is not int or value < 1:
                raise ValueError("Positive integer identifiers required")
        for name in ("starts_at", "preparation_at", "settled_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _utc(value))
        if self.preparation_at < self.starts_at:
            raise ValueError("Preparation cannot precede cycle start")
        if self.settled_at is not None and self.settled_at < self.replay_deadline:
            raise ValueError("Settlement cannot precede replay deadline")

    @classmethod
    def first(cls, *, season_id: int, rule_version: int, starts_at: datetime):
        starts_at = _utc(starts_at)
        return cls(
            season_id=season_id,
            rule_version=rule_version,
            number=1,
            starts_at=starts_at,
            preparation_at=starts_at + timedelta(hours=72),
        )

    @property
    def battle_at(self) -> datetime:
        return self.preparation_at + timedelta(hours=24)

    @property
    def battle_ends_at(self) -> datetime:
        return self.battle_at + timedelta(hours=48)

    @property
    def replay_deadline(self) -> datetime:
        return self.battle_ends_at + timedelta(minutes=5)

    @property
    def next_cycle_starts_at(self) -> datetime | None:
        if self.settled_at is None or self.season_end_requested:
            return None
        return self.settled_at + timedelta(hours=12)

    def phase_at(self, now: datetime) -> CyclePhase:
        now = _utc(now)
        if now < self.starts_at:
            raise ValueError("Cycle has not started")
        if now < self.preparation_at:
            return CyclePhase.REGISTRATION
        if now < self.battle_at:
            return CyclePhase.PREPARATION
        if now < self.battle_ends_at:
            return CyclePhase.BATTLE
        if now < self.replay_deadline:
            return CyclePhase.REPLAY_LOADING
        if self.settled_at is None or now < self.settled_at:
            return CyclePhase.SETTLEMENT
        if self.season_end_requested:
            return CyclePhase.SEASON_ENDED
        if now < self.next_cycle_starts_at:
            return CyclePhase.REST
        return CyclePhase.COMPLETE

    def settle(self, completed_at: datetime):
        """Called only after all dependent calculations have succeeded."""
        completed_at = _utc(completed_at)
        if self.settled_at is not None:
            return self
        if completed_at < self.replay_deadline:
            raise ValueError("Replay loading has not finished")
        return replace(self, settled_at=completed_at)

    def request_season_end(self):
        return replace(self, season_end_requested=True)

    def next_cycle(self, *, rule_version: int):
        preparation_at = self.next_cycle_starts_at
        if preparation_at is None:
            raise ValueError("Next cycle is not allowed")
        return CampaignCycle(
            season_id=self.season_id,
            rule_version=rule_version,
            number=self.number + 1,
            starts_at=preparation_at,
            preparation_at=preparation_at,
        )

    def accepts_match(self, started_at: datetime, ended_at: datetime) -> bool:
        started_at, ended_at = _utc(started_at), _utc(ended_at)
        return (
            self.battle_at <= started_at < self.battle_ends_at
            and ended_at <= self.battle_ends_at
            and ended_at - started_at >= timedelta(minutes=1)
        )

    def reinforcement_arrival(self, sent_at: datetime) -> datetime:
        sent_at = _utc(sent_at)
        if not self.battle_at <= sent_at < self.battle_at + timedelta(hours=24):
            raise ValueError("Reinforcements must be sent in the first 24 hours")
        return sent_at + timedelta(hours=24)
