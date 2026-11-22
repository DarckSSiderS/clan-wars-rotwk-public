from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.time import as_utc, utc_now
from app.models.clan import Clan
from app.models.clan_warfare import ClanAttackPointSpend, ClanLevelEvent
from app.models.war import ClanWar
from app.services.campaign_rule_service import CampaignRuleService, CampaignRuleSnapshot


@dataclass(frozen=True)
class AttackPointRecovery:
    spend_id: int
    recover_at: datetime
    war_id: int | None


@dataclass(frozen=True)
class ClanAttackPointStatus:
    capacity: int
    available: int
    recovering: int
    blocked: int
    next_attack_at: datetime | None
    recoveries: tuple[AttackPointRecovery, ...]


class AttackPointsExhausted(ValueError):
    code = "attack_points_exhausted"

    def __init__(self, status: ClanAttackPointStatus):
        self.status = status
        super().__init__("У клана нет доступных очков атаки")


class ClanAttackPointService:
    @staticmethod
    def _future_spends(
        db: Session,
        clan_id: int,
        *,
        now: datetime,
    ) -> list[ClanAttackPointSpend]:
        rows = (
            db.query(ClanAttackPointSpend)
            .filter(
                ClanAttackPointSpend.clan_id == clan_id,
                ClanAttackPointSpend.refunded_at.is_(None),
            )
            .all()
        )
        return sorted(
            (row for row in rows if as_utc(row.recover_at) > now),
            key=lambda row: (as_utc(row.recover_at), row.id or 0),
        )

    def status(
        self,
        db: Session,
        clan: Clan,
        *,
        capacity: int,
        now: datetime | None = None,
    ) -> ClanAttackPointStatus:
        now = as_utc(now) or utc_now()
        capacity = max(0, int(capacity))
        future_spends = self._future_spends(db, clan.id, now=now)
        recovering = len(future_spends)
        available = max(0, capacity - recovering)

        spend_capacities = [
            int(value[0])
            for value in db.query(ClanAttackPointSpend.capacity_snapshot)
            .filter(ClanAttackPointSpend.clan_id == clan.id)
            .all()
            if value[0] is not None
        ]
        achieved_levels = [
            int(value[0])
            for value in db.query(ClanLevelEvent.new_level)
            .filter(ClanLevelEvent.clan_id == clan.id)
            .all()
            if value[0] is not None
        ]
        historical_peak = max([capacity, *spend_capacities, *achieved_levels])
        blocked = max(0, historical_peak - capacity)
        recoveries = tuple(
            AttackPointRecovery(
                spend_id=spend.id,
                recover_at=as_utc(spend.recover_at),
                war_id=spend.war_id,
            )
            for spend in future_spends
        )
        next_attack_at = None if available > 0 else (
            recoveries[0].recover_at if recoveries else None
        )
        clan.next_attack_at = next_attack_at
        return ClanAttackPointStatus(
            capacity=capacity,
            available=available,
            recovering=recovering,
            blocked=blocked,
            next_attack_at=next_attack_at,
            recoveries=recoveries,
        )

    def spend(
        self,
        db: Session,
        clan: Clan,
        *,
        war: ClanWar,
        actor_user_id: int,
        level: int,
        capacity: int,
        rule_set: CampaignRuleSnapshot,
        now: datetime | None = None,
    ) -> ClanAttackPointSpend:
        now = as_utc(now) or utc_now()
        locked_clan = (
            db.query(Clan).filter(Clan.id == clan.id).with_for_update().one()
        )
        status = self.status(db, locked_clan, capacity=capacity, now=now)
        if status.available <= 0:
            raise AttackPointsExhausted(status)

        spend = ClanAttackPointSpend(
            clan_id=locked_clan.id,
            war_id=war.id,
            spent_by_user_id=actor_user_id,
            origin="war",
            spent_at=now,
            recover_at=now
            + timedelta(hours=int(rule_set.values["CLAN_ATTACK_COOLDOWN_HOURS"])),
            level_snapshot=int(level),
            capacity_snapshot=int(capacity),
            campaign_rule_set_id=rule_set.id,
            rule_version=rule_set.version,
        )
        db.add(spend)
        db.flush()
        self.status(db, locked_clan, capacity=capacity, now=now)
        return spend

    def create_legacy_spend(
        self,
        db: Session,
        clan: Clan,
        *,
        recover_at: datetime,
        rule_set: CampaignRuleSnapshot,
        now: datetime | None = None,
    ) -> ClanAttackPointSpend:
        spent_at = as_utc(now) or (
            as_utc(recover_at)
            - timedelta(hours=int(rule_set.values["CLAN_ATTACK_COOLDOWN_HOURS"]))
        )
        spend = ClanAttackPointSpend(
            clan_id=clan.id,
            war_id=None,
            spent_by_user_id=None,
            origin="legacy_next_attack_at",
            spent_at=spent_at,
            recover_at=as_utc(recover_at),
            level_snapshot=1,
            capacity_snapshot=1,
            campaign_rule_set_id=rule_set.id,
            rule_version=rule_set.version,
        )
        db.add(spend)
        db.flush()
        self.status(db, clan, capacity=1, now=spent_at)
        return spend

    def refund(
        self,
        db: Session,
        spend: ClanAttackPointSpend,
        *,
        actor_user_id: int | None,
        reason: str,
        now: datetime | None = None,
    ) -> ClanAttackPointSpend:
        if spend.refunded_at is not None:
            return spend
        refunded_at = as_utc(now) or utc_now()
        spend.refunded_at = refunded_at
        spend.refunded_by_user_id = actor_user_id
        spend.refund_reason = reason
        db.flush()
        self.sync_legacy_next_attack_at(db, spend.clan, now=refunded_at)
        return spend

    def refund_for_war(
        self,
        db: Session,
        war: ClanWar,
        *,
        actor_user_id: int | None,
        reason: str,
        now: datetime | None = None,
    ) -> ClanAttackPointSpend | None:
        refunded_at = as_utc(now) or utc_now()
        linked = (
            db.query(ClanAttackPointSpend)
            .filter(
                ClanAttackPointSpend.war_id == war.id,
                ClanAttackPointSpend.clan_id == war.attacking_clan_id,
                ClanAttackPointSpend.refunded_at.is_(None),
            )
            .one_or_none()
        )
        if linked is not None:
            return self.refund(
                db,
                linked,
                actor_user_id=actor_user_id,
                reason=reason,
                now=refunded_at,
            )
        if war.scoring_version != "elo_team_v2":
            return None

        legacy_rows = (
            db.query(ClanAttackPointSpend)
            .filter(
                ClanAttackPointSpend.clan_id == war.attacking_clan_id,
                ClanAttackPointSpend.origin == "legacy_next_attack_at",
                ClanAttackPointSpend.refunded_at.is_(None),
            )
            .all()
        )
        future_rows = [
            row for row in legacy_rows if as_utc(row.recover_at) > refunded_at
        ]
        if not future_rows:
            return None
        legacy = min(future_rows, key=lambda row: as_utc(row.recover_at))
        return self.refund(
            db,
            legacy,
            actor_user_id=actor_user_id,
            reason=reason,
            now=refunded_at,
        )

    def sync_legacy_next_attack_at(
        self,
        db: Session,
        clan: Clan,
        *,
        now: datetime | None = None,
    ) -> None:
        rule_set = CampaignRuleService().get_active(db)
        level = min(5, max(1, int(clan.level or 1)))
        capacity = int(rule_set.values[f"CLAN_LEVEL_{level}_ATTACK_CAPACITY"])
        self.status(db, clan, capacity=capacity, now=now)
