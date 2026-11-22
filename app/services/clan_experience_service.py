from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session

from app.core.time import as_utc, utc_now
from app.models.clan import ClanMember, ClanMembershipPeriod
from app.models.external_identity import ExternalPlayerAlias, ExternalPlayerIdentity
from app.models.match import Match
from app.models.user import User
from app.models.war import ClanWarMatchResult
from app.services.match_eligibility_service import is_ranked_1v1_eligible
from app.services.campaign_rule_service import CampaignRuleService


MOSCOW_TZ = ZoneInfo("Europe/Moscow")


class ClanExperienceService:
    """Calculates clan-specific experience without mutating profile experience."""

    MATCH_EXPERIENCE = 10
    WIN_EXPERIENCE = 5
    WAR_MATCH_EXPERIENCE = 20
    WAR_POINT_EXPERIENCE = 10
    ACTIVITY_DAYS_CAP = 12
    ACTIVITY_BONUS_CAP = 0.50
    LOYALTY_DAYS_CAP = 180
    LOYALTY_BONUS_CAP = 0.25
    OPPONENTS_CAP = 15
    DIVERSITY_BONUS_CAP = 0.15

    def calculate(
        self,
        db: Session,
        user: User,
        clan_id: int,
        *,
        now: datetime | None = None,
    ) -> dict:
        now = as_utc(now) or utc_now()
        rules = CampaignRuleService().get_active(db).values
        periods = self._membership_periods(db, user.id, clan_id)
        if not periods:
            return self.empty_result()

        names, external_uuids = self._player_identity_keys(db, user)
        matches = self._eligible_membership_matches(
            db,
            names,
            external_uuids,
            periods,
            rules,
        )
        wins = 0
        recent_activity_days = set()
        opponents = set()
        recent_cutoff = now - timedelta(days=30)

        for match in matches:
            player_won = self._is_winner(match, names, external_uuids)
            if player_won:
                wins += 1
                opponent_name = match.loser_player
                opponent_uuid = match.loser_player_uuid
            else:
                opponent_name = match.winner_player
                opponent_uuid = match.winner_player_uuid
            opponents.add(opponent_uuid or str(opponent_name).strip().lower())
            played_at = as_utc(match.match_date)
            if played_at and recent_cutoff <= played_at <= now:
                recent_activity_days.add(
                    played_at.astimezone(MOSCOW_TZ).date()
                )

        war_results = (
            db.query(ClanWarMatchResult)
            .filter(
                ClanWarMatchResult.is_counted.is_(True),
                or_(
                    (
                        (ClanWarMatchResult.winner_user_id == user.id)
                        & (ClanWarMatchResult.winner_clan_id == clan_id)
                    ),
                    (
                        (ClanWarMatchResult.loser_user_id == user.id)
                        & (ClanWarMatchResult.loser_clan_id == clan_id)
                    ),
                ),
            )
            .all()
        )
        war_wins = sum(
            1
            for result in war_results
            if result.winner_user_id == user.id
            and result.winner_clan_id == clan_id
        )
        war_points = round(
            sum(
                result.winner_total_points
                if result.winner_user_id == user.id
                and result.winner_clan_id == clan_id
                else result.loser_total_points
                for result in war_results
            ),
            2,
        )
        membership_days = self._membership_days(periods, now)
        activity_coefficient = 1 + min(
            self.ACTIVITY_BONUS_CAP,
            len(recent_activity_days)
            / self.ACTIVITY_DAYS_CAP
            * self.ACTIVITY_BONUS_CAP,
        )
        loyalty_coefficient = 1 + min(
            self.LOYALTY_BONUS_CAP,
            membership_days
            / self.LOYALTY_DAYS_CAP
            * self.LOYALTY_BONUS_CAP,
        )
        diversity_coefficient = 1 + min(
            self.DIVERSITY_BONUS_CAP,
            len(opponents)
            / self.OPPONENTS_CAP
            * self.DIVERSITY_BONUS_CAP,
        )
        base_experience = (
            len(matches) * self.MATCH_EXPERIENCE
            + wins * self.WIN_EXPERIENCE
            + len(war_results) * self.WAR_MATCH_EXPERIENCE
            + war_points * self.WAR_POINT_EXPERIENCE
        )
        clan_experience = round(
            base_experience
            * activity_coefficient
            * loyalty_coefficient
            * diversity_coefficient
        )
        return {
            "clan_experience": clan_experience,
            "clan_matches": len(matches),
            "clan_wins": wins,
            "clan_losses": len(matches) - wins,
            "clan_war_matches": len(war_results),
            "clan_war_wins": war_wins,
            "clan_war_points": war_points,
            "active_days_30": len(recent_activity_days),
            "membership_days": round(membership_days, 1),
            "unique_opponents": len(opponents),
            "base_experience": round(base_experience, 2),
            "activity_coefficient": round(activity_coefficient, 3),
            "loyalty_coefficient": round(loyalty_coefficient, 3),
            "diversity_coefficient": round(diversity_coefficient, 3),
        }

    @staticmethod
    def empty_result() -> dict:
        return {
            "clan_experience": 0,
            "clan_matches": 0,
            "clan_wins": 0,
            "clan_losses": 0,
            "clan_war_matches": 0,
            "clan_war_wins": 0,
            "clan_war_points": 0,
            "active_days_30": 0,
            "membership_days": 0,
            "unique_opponents": 0,
            "base_experience": 0,
            "activity_coefficient": 1,
            "loyalty_coefficient": 1,
            "diversity_coefficient": 1,
        }

    @staticmethod
    def _membership_periods(
        db: Session,
        user_id: int,
        clan_id: int,
    ) -> list[ClanMembershipPeriod]:
        periods = (
            db.query(ClanMembershipPeriod)
            .filter(
                ClanMembershipPeriod.user_id == user_id,
                ClanMembershipPeriod.clan_id == clan_id,
            )
            .order_by(ClanMembershipPeriod.started_at.asc())
            .all()
        )
        if periods:
            return periods
        member = (
            db.query(ClanMember)
            .filter(
                ClanMember.user_id == user_id,
                ClanMember.clan_id == clan_id,
            )
            .first()
        )
        if not member:
            return []
        return [
            ClanMembershipPeriod(
                user_id=user_id,
                clan_id=clan_id,
                started_at=member.joined_at,
                started_reason="legacy_fallback",
            )
        ]

    @staticmethod
    def _player_identity_keys(db: Session, user: User) -> tuple[set[str], set[str]]:
        names = {user.username}
        external_uuids = set()
        identities = (
            db.query(ExternalPlayerIdentity)
            .filter(ExternalPlayerIdentity.user_id == user.id)
            .all()
        )
        identity_ids = []
        for identity in identities:
            names.add(identity.current_nickname)
            external_uuids.add(identity.external_uuid)
            identity_ids.append(identity.id)
        if identity_ids:
            aliases = (
                db.query(ExternalPlayerAlias)
                .filter(ExternalPlayerAlias.identity_id.in_(identity_ids))
                .all()
            )
            names.update(alias.nickname for alias in aliases)
        return names, external_uuids

    def _eligible_membership_matches(
        self,
        db: Session,
        names: set[str],
        external_uuids: set[str],
        periods: list[ClanMembershipPeriod],
        rules,
    ) -> list[Match]:
        keys = {name.strip().lower() for name in names}
        identity_filters = [or_(uuid.in_(external_uuids), and_(
            or_(uuid.is_(None), uuid == ''), func.lower(func.trim(name)).in_(keys),
        )) for name, uuid in ((Match.winner_player, Match.winner_player_uuid),
                             (Match.loser_player, Match.loser_player_uuid))]
        candidates = db.query(Match).filter(or_(*identity_filters)).all()
        return [
            match
            for match in candidates
            if is_ranked_1v1_eligible(match, rules=rules)
            and self._played_during_membership(match.match_date, periods)
        ]

    @staticmethod
    def _played_during_membership(
        played_at: datetime,
        periods: list[ClanMembershipPeriod],
    ) -> bool:
        played_at = as_utc(played_at)
        return any(
            as_utc(period.started_at) <= played_at
            and (
                period.ended_at is None
                or played_at < as_utc(period.ended_at)
            )
            for period in periods
        )

    @staticmethod
    def _is_winner(
        match: Match,
        names: set[str],
        external_uuids: set[str],
    ) -> bool:
        if match.winner_player_uuid:
            return match.winner_player_uuid in external_uuids
        return str(match.winner_player or '').strip().lower() in {name.strip().lower() for name in names}

    @staticmethod
    def _membership_days(
        periods: list[ClanMembershipPeriod],
        now: datetime,
    ) -> float:
        total_seconds = 0.0
        for period in periods:
            started_at = as_utc(period.started_at)
            ended_at = as_utc(period.ended_at) or now
            if ended_at > started_at:
                total_seconds += (min(ended_at, now) - started_at).total_seconds()
        return max(0.0, total_seconds / 86400)
