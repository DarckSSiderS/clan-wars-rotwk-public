from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.time import as_utc, utc_now
from app.models.clan import Clan, ClanMember, ClanMembershipPeriod
from app.models.clan_warfare import ClanLevelEvent
from app.models.external_identity import ExternalPlayerIdentity
from app.models.match import Match
from app.models.territory import Territory
from app.services.campaign_rule_service import CampaignRuleSnapshot
from app.services.elo_service import PATCH_202, PATCH_ENNORATH, get_patch_family
from app.services.match_eligibility_service import ranked_match_rejection_reason


@dataclass(frozen=True)
class ClanLevelThreshold:
    level: int
    attack_capacity: int
    active_members: int
    territories: int
    influence: int


@dataclass(frozen=True)
class ClanLevelStatus:
    level: int
    attack_capacity: int
    active_member_count: int
    territory_count: int
    influence: int
    next_level: ClanLevelThreshold | None
    missing: dict[str, int]


class ClanLevelService:
    @staticmethod
    def thresholds(rules: Mapping[str, int | float]) -> tuple[ClanLevelThreshold, ...]:
        rows = [
            ClanLevelThreshold(
                level=1,
                attack_capacity=int(rules["CLAN_LEVEL_1_ATTACK_CAPACITY"]),
                active_members=0,
                territories=0,
                influence=0,
            )
        ]
        for level in range(2, 6):
            prefix = f"CLAN_LEVEL_{level}"
            rows.append(
                ClanLevelThreshold(
                    level=level,
                    attack_capacity=int(rules[f"{prefix}_ATTACK_CAPACITY"]),
                    active_members=int(rules[f"{prefix}_ACTIVE_MEMBERS"]),
                    territories=int(rules[f"{prefix}_TERRITORIES"]),
                    influence=int(rules[f"{prefix}_INFLUENCE"]),
                )
            )
        return tuple(rows)

    @staticmethod
    def _played_during_periods(
        played_at: datetime,
        periods: list[ClanMembershipPeriod],
        member: ClanMember,
    ) -> bool:
        played_at = as_utc(played_at)
        if periods:
            return any(
                as_utc(period.started_at) <= played_at
                and (period.ended_at is None or played_at < as_utc(period.ended_at))
                for period in periods
            )
        return member.joined_at is None or as_utc(member.joined_at) <= played_at

    @staticmethod
    def _identity_played_match(identity: ExternalPlayerIdentity, match: Match) -> bool:
        aliases = {
            identity.current_nickname.casefold(),
            *(alias.nickname.casefold() for alias in identity.aliases),
        }
        participants = list(match.participants or [])
        if participants:
            for participant in participants:
                if participant.is_observer:
                    continue
                if participant.player_uuid:
                    if participant.player_uuid == identity.external_uuid:
                        return True
                    continue
                if participant.nickname and participant.nickname.casefold() in aliases:
                    return True
            return False

        legacy_sides = (
            (match.winner_player_uuid, match.winner_player),
            (match.loser_player_uuid, match.loser_player),
        )
        for player_uuid, nickname in legacy_sides:
            if player_uuid:
                if player_uuid == identity.external_uuid:
                    return True
                continue
            if nickname and nickname.casefold() in aliases:
                return True
        return False

    def activity_by_member(
        self,
        db: Session,
        clan_id: int,
        *,
        rules: Mapping[str, int | float],
        now: datetime,
    ) -> dict[int, int]:
        now = as_utc(now) or utc_now()
        cutoff = now - timedelta(days=int(rules["CLAN_ACTIVITY_WINDOW_DAYS"]))
        members = db.query(ClanMember).filter(ClanMember.clan_id == clan_id).all()
        activity = {member.user_id: 0 for member in members}
        if not members:
            return activity

        member_by_user = {member.user_id: member for member in members}
        user_ids = tuple(member_by_user)
        identities = (
            db.query(ExternalPlayerIdentity)
            .filter(
                ExternalPlayerIdentity.user_id.in_(user_ids),
                ExternalPlayerIdentity.verification_status == "verified",
            )
            .all()
        )
        identity_by_user = {identity.user_id: identity for identity in identities}
        if not identity_by_user:
            return activity

        periods_by_user: dict[int, list[ClanMembershipPeriod]] = {
            user_id: [] for user_id in identity_by_user
        }
        periods = (
            db.query(ClanMembershipPeriod)
            .filter(
                ClanMembershipPeriod.clan_id == clan_id,
                ClanMembershipPeriod.user_id.in_(tuple(identity_by_user)),
            )
            .all()
        )
        for period in periods:
            periods_by_user[period.user_id].append(period)

        # Match dates are historically stored both as naive UTC and aware UTC.
        # A broad database range keeps the query bounded; exact UTC boundaries
        # are enforced below in Python.
        matches = (
            db.query(Match)
            .filter(
                Match.match_date >= cutoff.replace(tzinfo=None),
                Match.match_date <= now.replace(tzinfo=None),
            )
            .all()
        )
        counted: dict[int, set[int]] = {user_id: set() for user_id in identity_by_user}
        for match in matches:
            played_at = as_utc(match.match_date)
            if played_at is None or played_at < cutoff or played_at > now:
                continue
            if get_patch_family(match.patch_name or match.patch_version, match.patch_id) not in {
                PATCH_202,
                PATCH_ENNORATH,
            }:
                continue
            if ranked_match_rejection_reason(match, rules=rules) is not None:
                continue
            for user_id, identity in identity_by_user.items():
                if not self._played_during_periods(
                    played_at,
                    periods_by_user[user_id],
                    member_by_user[user_id],
                ):
                    continue
                if self._identity_played_match(identity, match):
                    counted[user_id].add(match.id)

        for user_id, match_ids in counted.items():
            activity[user_id] = len(match_ids)
        return activity

    def evaluate(
        self,
        db: Session,
        clan: Clan,
        *,
        rule_set: CampaignRuleSnapshot,
        now: datetime | None = None,
        record: bool = True,
    ) -> ClanLevelStatus:
        now = as_utc(now) or utc_now()
        thresholds = self.thresholds(rule_set.values)
        # Уровень зависит от всего текущего состава. Игровая активность остаётся
        # справочной статистикой и не исключает участника из развития клана.
        active_member_count = (
            db.query(ClanMember).filter(ClanMember.clan_id == clan.id).count()
        )
        territory_count = (
            db.query(Territory).filter(Territory.owner_clan_id == clan.id).count()
        )
        influence = int(clan.territory_points or 0)

        selected = thresholds[0]
        for threshold in reversed(thresholds):
            if (
                active_member_count >= threshold.active_members
                and territory_count >= threshold.territories
                and influence >= threshold.influence
            ):
                selected = threshold
                break

        next_level = next(
            (threshold for threshold in thresholds if threshold.level == selected.level + 1),
            None,
        )
        missing = {}
        if next_level is not None:
            missing = {
                "active_members": max(0, next_level.active_members - active_member_count),
                "territories": max(0, next_level.territories - territory_count),
                "influence": max(0, next_level.influence - influence),
            }

        previous_level = int(clan.level or 1)
        if record and previous_level != selected.level:
            clan.level = selected.level
            db.add(
                ClanLevelEvent(
                    clan_id=clan.id,
                    previous_level=previous_level,
                    new_level=selected.level,
                    active_member_count=active_member_count,
                    territory_count=territory_count,
                    influence=influence,
                    campaign_rule_set_id=rule_set.id,
                    rule_version=rule_set.version,
                    reason="thresholds_recalculated",
                    occurred_at=now,
                )
            )
            db.flush()

        return ClanLevelStatus(
            level=selected.level,
            attack_capacity=selected.attack_capacity,
            active_member_count=active_member_count,
            territory_count=territory_count,
            influence=influence,
            next_level=next_level,
            missing=missing,
        )
