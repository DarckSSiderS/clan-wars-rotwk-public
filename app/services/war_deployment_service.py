from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import as_utc, utc_now
from app.models.clan import Clan, ClanMember, ClanMembershipPeriod
from app.models.external_identity import ExternalPlayerIdentity
from app.models.territory import Territory
from app.models.user import User
from app.models.war import ClanWar, ClanWarParticipant
from app.models.war_deployment import WarDeployment, WarDeploymentMember
from app.services.campaign_rule_service import CampaignRuleSnapshot


@dataclass(frozen=True)
class DeploymentCandidate:
    user_id: int
    username: str
    avatar_url: str | None
    nickname: str
    verified: bool
    activity_matches: int
    is_warlord: bool
    busy_in_attack: bool
    busy_war_id: int | None


@dataclass(frozen=True)
class EligibleWarSide:
    deployment_id: int | None
    scope: Literal["squad", "whole_clan"]
    users: tuple[User, ...]
    eligibility_code: str


class SquadValidationError(ValueError):
    def __init__(self, code: str, user_ids: Sequence[int] = ()):
        self.code = code
        self.user_ids = tuple(user_ids)
        super().__init__(code)


class DeploymentConflict(SquadValidationError):
    def __init__(self, user_ids: Sequence[int]):
        super().__init__("squad_member_busy", user_ids)


class WarDeploymentService:
    @staticmethod
    def _identities_by_user(
        db: Session,
        user_ids: Sequence[int],
    ) -> dict[int, ExternalPlayerIdentity]:
        if not user_ids:
            return {}
        identities = (
            db.query(ExternalPlayerIdentity)
            .filter(ExternalPlayerIdentity.user_id.in_(tuple(user_ids)))
            .all()
        )
        result: dict[int, ExternalPlayerIdentity] = {}
        for identity in identities:
            current = result.get(identity.user_id)
            if current is None or (
                current.verification_status != "verified"
                and identity.verification_status == "verified"
            ):
                result[identity.user_id] = identity
        return result

    def candidates(
        self,
        db: Session,
        clan_id: int,
        *,
        activity: Mapping[int, int],
    ) -> list[DeploymentCandidate]:
        members = db.query(ClanMember).filter(ClanMember.clan_id == clan_id).all()
        if not members:
            return []
        user_ids = [member.user_id for member in members]
        users = {
            user.id: user
            for user in db.query(User).filter(User.id.in_(tuple(user_ids))).all()
        }
        identities = self._identities_by_user(db, user_ids)
        busy_rows = (
            db.query(WarDeploymentMember, WarDeployment)
            .join(WarDeployment, WarDeployment.id == WarDeploymentMember.deployment_id)
            .filter(
                WarDeploymentMember.user_id.in_(tuple(user_ids)),
                WarDeploymentMember.released_at.is_(None),
            )
            .all()
        )
        busy = {member.user_id: deployment.war_id for member, deployment in busy_rows}
        candidates = []
        for member in members:
            user = users.get(member.user_id)
            if user is None:
                continue
            identity = identities.get(user.id)
            candidates.append(
                DeploymentCandidate(
                    user_id=user.id,
                    username=user.username,
                    avatar_url=user.avatar_url,
                    nickname=identity.current_nickname if identity else user.username,
                    verified=bool(
                        identity and identity.verification_status == "verified"
                    ),
                    activity_matches=int(activity.get(user.id, 0)),
                    is_warlord=bool(member.is_warlord),
                    busy_in_attack=user.id in busy,
                    busy_war_id=busy.get(user.id),
                )
            )
        return sorted(
            candidates,
            key=lambda candidate: (candidate.nickname.casefold(), candidate.user_id),
        )

    def validate_squad(
        self,
        db: Session,
        clan_id: int,
        user_ids: Sequence[int],
        *,
        minimum_size: int,
        warlord_user_id: int,
    ) -> list[tuple[ClanMember, ExternalPlayerIdentity]]:
        requested = [int(user_id) for user_id in user_ids]
        if len(set(requested)) != len(requested):
            raise SquadValidationError("squad_duplicate_members", requested)
        if len(requested) < int(minimum_size):
            raise SquadValidationError("squad_too_small", requested)

        members = (
            db.query(ClanMember)
            .filter(
                ClanMember.clan_id == clan_id,
                ClanMember.user_id.in_(tuple(requested)),
            )
            .all()
        )
        member_by_user = {member.user_id: member for member in members}
        missing = [user_id for user_id in requested if user_id not in member_by_user]
        if missing:
            raise SquadValidationError("squad_member_not_in_clan", missing)

        identities = self._identities_by_user(db, requested)
        unverified = [
            user_id
            for user_id in requested
            if user_id not in identities
            or identities[user_id].verification_status != "verified"
        ]
        if unverified:
            raise SquadValidationError("squad_member_unverified", unverified)

        busy = [
            user_id
            for (user_id,) in db.query(WarDeploymentMember.user_id)
            .filter(
                WarDeploymentMember.user_id.in_(tuple(requested)),
                WarDeploymentMember.released_at.is_(None),
            )
            .all()
        ]
        if busy:
            raise DeploymentConflict(busy)
        squad = [
            (member_by_user[user_id], identities[user_id]) for user_id in requested
        ]
        if int(warlord_user_id) not in requested:
            raise SquadValidationError("warlord_not_in_squad", [warlord_user_id])
        if not member_by_user[int(warlord_user_id)].is_warlord:
            raise SquadValidationError("warlord_not_assigned", [warlord_user_id])
        return squad

    @staticmethod
    def _membership_started_at(
        db: Session,
        member: ClanMember,
        *,
        assigned_at: datetime,
    ) -> datetime:
        period = (
            db.query(ClanMembershipPeriod)
            .filter(
                ClanMembershipPeriod.user_id == member.user_id,
                ClanMembershipPeriod.clan_id == member.clan_id,
                ClanMembershipPeriod.ended_at.is_(None),
            )
            .order_by(ClanMembershipPeriod.started_at.desc())
            .first()
        )
        return as_utc(
            period.started_at if period else member.joined_at
        ) or assigned_at

    def create_attack(
        self,
        db: Session,
        war: ClanWar,
        clan: Clan,
        members: Sequence[tuple[ClanMember, ExternalPlayerIdentity]],
        *,
        source_territory_id: int | None,
        territory_count: int,
        actor_user_id: int,
        rule_set: CampaignRuleSnapshot,
        claim_sequence: int,
        warlord_user_id: int,
    ) -> WarDeployment:
        assigned_at = utc_now()
        defense_rule = (
            "whole_clan_if_challenged"
            if int(territory_count) == 0
            else "squad_if_challenged"
        )
        deployment = WarDeployment(
            war_id=war.id,
            clan_id=clan.id,
            claim_sequence=claim_sequence,
            source_territory_id=source_territory_id,
            territory_count_snapshot=int(territory_count),
            defense_rule=defense_rule,
            initial_role="attacker",
            current_role="attacker",
            eligibility_scope="squad",
            assigned_by_user_id=actor_user_id,
            warlord_user_id=warlord_user_id,
            warlord_username_snapshot=next(
                member.user.username
                for member, _ in members
                if member.user_id == warlord_user_id
            ),
            assigned_at=assigned_at,
            campaign_rule_set_id=rule_set.id,
            rule_version=rule_set.version,
        )
        db.add(deployment)
        db.flush()

        rows = []
        for member, identity in members:
            rows.append(
                WarDeploymentMember(
                    deployment_id=deployment.id,
                    user_id=member.user_id,
                    external_uuid_snapshot=identity.external_uuid,
                    nickname_snapshot=identity.current_nickname,
                    username_snapshot=member.user.username,
                    avatar_url_snapshot=member.user.avatar_url,
                    membership_started_at=self._membership_started_at(
                        db,
                        member,
                        assigned_at=assigned_at,
                    ),
                    assigned_at=assigned_at,
                )
            )
        try:
            with db.begin_nested():
                db.add_all(rows)
                db.flush()
        except IntegrityError as exc:
            requested = [member.user_id for member, _ in members]
            busy = [
                user_id
                for (user_id,) in db.query(WarDeploymentMember.user_id)
                .filter(
                    WarDeploymentMember.user_id.in_(tuple(requested)),
                    WarDeploymentMember.released_at.is_(None),
                )
                .all()
            ]
            raise DeploymentConflict(busy or requested) from exc
        return deployment

    def transition_neutral_claim_to_defense(
        self,
        db: Session,
        deployment: WarDeployment,
        *,
        now: datetime,
    ) -> WarDeployment:
        changed_at = as_utc(now) or utc_now()
        deployment.current_role = "defender"
        deployment.role_changed_at = changed_at
        deployment.eligibility_scope = (
            "whole_clan"
            if deployment.defense_rule == "whole_clan_if_challenged"
            else "squad"
        )
        self.release_attack_lock(db, deployment, now=changed_at)
        db.flush()
        return deployment

    def create_whole_clan_defense(
        self,
        db: Session,
        war: ClanWar,
        clan_id: int,
        *,
        defense_rule: str,
        rule_set: CampaignRuleSnapshot,
        now: datetime,
    ) -> WarDeployment:
        assigned_at = as_utc(now) or utc_now()
        max_sequence = (
            db.query(func.max(WarDeployment.claim_sequence))
            .filter(WarDeployment.war_id == war.id)
            .scalar()
        )
        territory_count = (
            db.query(Territory).filter(Territory.owner_clan_id == clan_id).count()
        )
        deployment = WarDeployment(
            war_id=war.id,
            clan_id=clan_id,
            claim_sequence=(max_sequence or 1) + 1,
            source_territory_id=None,
            territory_count_snapshot=territory_count,
            defense_rule=defense_rule,
            initial_role="defender",
            current_role="defender",
            eligibility_scope="whole_clan",
            assigned_by_user_id=None,
            assigned_at=assigned_at,
            campaign_rule_set_id=rule_set.id,
            rule_version=rule_set.version,
            attack_lock_released_at=assigned_at,
        )
        db.add(deployment)
        db.flush()
        return deployment

    @staticmethod
    def release_attack_lock(
        db: Session,
        deployment: WarDeployment,
        *,
        now: datetime,
    ) -> None:
        released_at = as_utc(now) or utc_now()
        if deployment.attack_lock_released_at is None:
            deployment.attack_lock_released_at = released_at
        for member in deployment.members:
            if member.released_at is None:
                member.released_at = released_at
        db.flush()

    @staticmethod
    def _member_ids_at(
        db: Session,
        clan_id: int,
        played_at: datetime,
        user_ids: set[int] | None = None,
    ) -> set[int]:
        query = db.query(ClanMembershipPeriod).filter(
            ClanMembershipPeriod.clan_id == clan_id
        )
        if user_ids is not None:
            if not user_ids:
                return set()
            query = query.filter(ClanMembershipPeriod.user_id.in_(tuple(user_ids)))
        periods = query.all()
        matching = {
            period.user_id
            for period in periods
            if as_utc(period.started_at) <= played_at
            and (period.ended_at is None or played_at < as_utc(period.ended_at))
        }
        if matching or periods:
            return matching

        legacy = db.query(ClanMember).filter(ClanMember.clan_id == clan_id)
        if user_ids is not None:
            legacy = legacy.filter(ClanMember.user_id.in_(tuple(user_ids)))
        return {
            member.user_id
            for member in legacy.all()
            if member.joined_at is None or as_utc(member.joined_at) <= played_at
        }

    def eligible_side(
        self,
        db: Session,
        war: ClanWar,
        clan_id: int,
        played_at: datetime,
    ) -> EligibleWarSide:
        played_at = as_utc(played_at) or utc_now()
        deployment = (
            db.query(WarDeployment)
            .filter(
                WarDeployment.war_id == war.id,
                WarDeployment.clan_id == clan_id,
            )
            .one_or_none()
        )
        if deployment is None:
            return EligibleWarSide(
                deployment_id=None,
                scope="whole_clan",
                users=(),
                eligibility_code="deployment_missing",
            )

        if deployment.eligibility_scope == "squad":
            snapshot_ids = {member.user_id for member in deployment.members}
            eligible_ids = self._member_ids_at(
                db,
                clan_id,
                played_at,
                snapshot_ids,
            )
            code = (
                "attack_squad_member"
                if deployment.current_role == "attacker"
                else "defending_squad_member"
            )
        else:
            verified_ids = {
                user_id
                for (user_id,) in db.query(ExternalPlayerIdentity.user_id)
                .filter(ExternalPlayerIdentity.verification_status == "verified")
                .all()
            }
            eligible_ids = self._member_ids_at(
                db,
                clan_id,
                played_at,
                verified_ids,
            )
            code = "defending_clan_member"

        users = {
            user.id: user
            for user in db.query(User).filter(User.id.in_(tuple(eligible_ids))).all()
        } if eligible_ids else {}
        return EligibleWarSide(
            deployment_id=deployment.id,
            scope=deployment.eligibility_scope,
            users=tuple(users[user_id] for user_id in sorted(users)),
            eligibility_code=code,
        )

    @staticmethod
    def _participant_metrics(db: Session, war_id: int) -> dict[int, dict]:
        rows = (
            db.query(ClanWarParticipant)
            .filter(ClanWarParticipant.war_id == war_id)
            .all()
        )
        return {
            row.user_id: {
                "matches": int(row.wins or 0) + int(row.losses or 0),
                "wins": int(row.wins or 0),
                "losses": int(row.losses or 0),
                "points": float(row.war_points or 0),
            }
            for row in rows
        }

    @staticmethod
    def _period_for_snapshot(
        periods: Sequence[ClanMembershipPeriod],
        membership_started_at: datetime,
    ) -> ClanMembershipPeriod | None:
        started_at = as_utc(membership_started_at)
        containing = [
            period
            for period in periods
            if as_utc(period.started_at) <= started_at
            and (period.ended_at is None or started_at < as_utc(period.ended_at))
        ]
        return max(containing, key=lambda period: as_utc(period.started_at), default=None)

    def _squad_group_members(
        self,
        db: Session,
        war: ClanWar,
        deployment: WarDeployment,
        metrics: Mapping[int, dict],
    ) -> list[dict]:
        user_ids = [member.user_id for member in deployment.members]
        users = {
            user.id: user
            for user in db.query(User).filter(User.id.in_(tuple(user_ids))).all()
        } if user_ids else {}
        identities = self._identities_by_user(db, user_ids)
        periods_by_user: dict[int, list[ClanMembershipPeriod]] = {
            user_id: [] for user_id in user_ids
        }
        if user_ids:
            for period in (
                db.query(ClanMembershipPeriod)
                .filter(
                    ClanMembershipPeriod.clan_id == deployment.clan_id,
                    ClanMembershipPeriod.user_id.in_(tuple(user_ids)),
                )
                .all()
            ):
                periods_by_user[period.user_id].append(period)
        effective_end = as_utc(war.ended_at) or utc_now()
        result = []
        for snapshot in deployment.members:
            user = users.get(snapshot.user_id)
            identity = identities.get(snapshot.user_id)
            period = self._period_for_snapshot(
                periods_by_user.get(snapshot.user_id, []),
                snapshot.membership_started_at,
            )
            membership_ended_at = as_utc(period.ended_at) if period and period.ended_at else None
            if membership_ended_at and membership_ended_at <= effective_end:
                status_code = "left_clan"
            elif war.status != "active" and snapshot.released_at is not None:
                status_code = "deployment_released"
            else:
                status_code = "participating"
            result.append(
                {
                    "user_id": snapshot.user_id,
                    "username": user.username if user else snapshot.username_snapshot,
                    "display_nickname": (
                        identity.current_nickname
                        if identity else snapshot.nickname_snapshot
                    ),
                    "snapshot_nickname": snapshot.nickname_snapshot,
                    "avatar_url": (
                        user.avatar_url if user and user.avatar_url
                        else snapshot.avatar_url_snapshot
                    ),
                    "membership_started_at": as_utc(snapshot.membership_started_at),
                    "membership_ended_at": membership_ended_at,
                    "assigned_at": as_utc(snapshot.assigned_at),
                    "status_code": status_code,
                    **metrics.get(
                        snapshot.user_id,
                        {"matches": 0, "wins": 0, "losses": 0, "points": 0.0},
                    ),
                }
            )
        return result

    def _whole_clan_periods(
        self,
        db: Session,
        war: ClanWar,
        deployment: WarDeployment,
    ) -> dict[int, tuple[datetime, datetime | None]]:
        war_start = as_utc(war.started_at) or as_utc(deployment.assigned_at)
        if war.status == "active":
            members = (
                db.query(ClanMember)
                .filter(ClanMember.clan_id == deployment.clan_id)
                .all()
            )
            member_ids = [member.user_id for member in members]
            identities = self._identities_by_user(db, member_ids)
            verified_ids = {
                user_id
                for user_id, identity in identities.items()
                if identity.verification_status == "verified"
            }
            periods = (
                db.query(ClanMembershipPeriod)
                .filter(
                    ClanMembershipPeriod.clan_id == deployment.clan_id,
                    ClanMembershipPeriod.user_id.in_(tuple(verified_ids)),
                    ClanMembershipPeriod.ended_at.is_(None),
                )
                .all()
                if verified_ids else []
            )
            by_user = {
                period.user_id: (as_utc(period.started_at), None)
                for period in periods
            }
            for member in members:
                if member.user_id in verified_ids and member.user_id not in by_user:
                    by_user[member.user_id] = (
                        as_utc(member.joined_at) or war_start,
                        None,
                    )
            return by_user

        war_end = as_utc(war.ended_at) or as_utc(war.ends_at) or utc_now()
        periods = (
            db.query(ClanMembershipPeriod)
            .filter(ClanMembershipPeriod.clan_id == deployment.clan_id)
            .all()
        )
        by_user: dict[int, tuple[datetime, datetime | None]] = {}
        for period in periods:
            period_start = as_utc(period.started_at)
            period_end = as_utc(period.ended_at) if period.ended_at else None
            if period_start > war_end or (period_end and period_end <= war_start):
                continue
            clipped_start = max(period_start, war_start)
            clipped_end = min(period_end, war_end) if period_end else None
            existing = by_user.get(period.user_id)
            if existing is None:
                by_user[period.user_id] = (clipped_start, clipped_end)
            else:
                existing_start, existing_end = existing
                by_user[period.user_id] = (
                    min(existing_start, clipped_start),
                    None
                    if existing_end is None or clipped_end is None
                    else max(existing_end, clipped_end),
                )
        return by_user

    def _whole_clan_group_members(
        self,
        db: Session,
        war: ClanWar,
        deployment: WarDeployment,
        metrics: Mapping[int, dict],
    ) -> list[dict]:
        periods = self._whole_clan_periods(db, war, deployment)
        user_ids = tuple(periods)
        users = {
            user.id: user
            for user in db.query(User).filter(User.id.in_(user_ids)).all()
        } if user_ids else {}
        identities = self._identities_by_user(db, user_ids)
        war_start = as_utc(war.started_at) or as_utc(deployment.assigned_at)
        members = []
        for user_id, (started_at, ended_at) in sorted(
            periods.items(),
            key=lambda item: (item[1][0], item[0]),
        ):
            user = users.get(user_id)
            if user is None:
                continue
            identity = identities.get(user_id)
            if ended_at is not None:
                status_code = "left_clan"
            elif started_at > war_start:
                status_code = "joined_during_war"
            else:
                status_code = "participating"
            members.append(
                {
                    "user_id": user.id,
                    "username": user.username,
                    "display_nickname": (
                        identity.current_nickname if identity else user.username
                    ),
                    "snapshot_nickname": None,
                    "avatar_url": user.avatar_url,
                    "membership_started_at": started_at,
                    "membership_ended_at": ended_at,
                    "assigned_at": None,
                    "status_code": status_code,
                    **metrics.get(
                        user.id,
                        {"matches": 0, "wins": 0, "losses": 0, "points": 0.0},
                    ),
                }
            )
        return members

    def public_side_groups(self, db: Session, war: ClanWar) -> list[dict]:
        if war.scoring_version != "elo_team_v3_squads":
            return []
        metrics = self._participant_metrics(db, war.id)
        groups = []
        for deployment in sorted(
            war.deployments,
            key=lambda item: (
                0 if item.current_role == "attacker" else 1,
                item.claim_sequence,
            ),
        ):
            clan = deployment.clan
            members = (
                self._squad_group_members(db, war, deployment, metrics)
                if deployment.eligibility_scope == "squad"
                else self._whole_clan_group_members(db, war, deployment, metrics)
            )
            groups.append(
                {
                    "clan_id": deployment.clan_id,
                    "clan_name": clan.name if clan else f"Клан #{deployment.clan_id}",
                    "clan_avatar_url": clan.avatar_url if clan else None,
                    "clan_map_color": clan.map_color if clan else None,
                    "role": deployment.current_role,
                    "scope": deployment.eligibility_scope,
                    "defense_rule": deployment.defense_rule,
                    "warlord_user_id": deployment.warlord_user_id,
                    "warlord_username": deployment.warlord_username_snapshot,
                    "member_count": len(members),
                    "members": members,
                }
            )
        return groups
