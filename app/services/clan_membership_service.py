from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.time import as_utc, utc_now
from app.models.clan import Clan, ClanMember, ClanMembershipPeriod


class ClanMembershipService:
    """Хранит периоды членства в клане для расчёта очков в битвах."""

    @staticmethod
    def continuous_member_since(db, *, user_id, clan_id, since, occurred_at):
        """Для зачёта нужно непрерывное членство от раскрытия приказов до начала матча."""
        since, occurred_at = as_utc(since), as_utc(occurred_at)
        if since is None or occurred_at is None or occurred_at < since:
            return False
        periods = db.query(ClanMembershipPeriod).filter_by(user_id=user_id).all()
        if periods:
            crossing = [period for period in periods if as_utc(period.started_at) <= occurred_at
                and (period.ended_at is None or since < as_utc(period.ended_at))]
            return (len(crossing) == 1 and crossing[0].clan_id == clan_id
                and as_utc(crossing[0].started_at) <= since
                and (crossing[0].ended_at is None or occurred_at < as_utc(crossing[0].ended_at)))
        # Совместимость с составами, созданными до заполнения истории членства.
        members = db.query(ClanMember).filter_by(user_id=user_id).all()
        return (len(members) == 1 and members[0].clan_id == clan_id
            and members[0].joined_at is not None and as_utc(members[0].joined_at) <= since)

    @staticmethod
    def dispatched_member_since(db, *, user_id, clan_id, since, occurred_at, dispatch=None):
        """Удаление отправителя не отменяет уже отправленную союзную помощь."""
        if ClanMembershipService.continuous_member_since(db, user_id=user_id, clan_id=clan_id,
                since=since, occurred_at=occurred_at):
            return True
        since, occurred_at = as_utc(since), as_utc(occurred_at)
        if (dispatch is None or dispatch.sender_clan_id != clan_id
                or dispatch.recipient_clan_id == clan_id or since is None or occurred_at is None
                or not since <= as_utc(dispatch.sent_at) <= occurred_at):
            return False
        clan = db.get(Clan, clan_id)
        current = db.query(ClanMember.id).filter(ClanMember.user_id == user_id,
            or_(ClanMember.joined_at.is_(None), ClanMember.joined_at <= occurred_at)).first()
        if clan is None or not clan.is_deleted or current:
            return False
        periods = db.query(ClanMembershipPeriod).filter_by(user_id=user_id).all()
        crossing = [period for period in periods if as_utc(period.started_at) <= occurred_at
            and (period.ended_at is None or since < as_utc(period.ended_at))]
        if len(crossing) != 1:
            return False
        period = crossing[0]
        return (period.clan_id == clan_id and as_utc(period.started_at) <= since
            and period.ended_reason == 'clan_deleted' and period.ended_at is not None
            and as_utc(dispatch.sent_at) <= as_utc(period.ended_at) <= occurred_at)

    def start(
        self,
        db: Session,
        member: ClanMember,
        *,
        reason: str = "joined",
        started_at: datetime | None = None,
    ) -> ClanMembershipPeriod:
        from app.services.preseason_service import PreseasonService
        PreseasonService().lock_rosters(db)
        active = (
            db.query(ClanMembershipPeriod)
            .filter(
                ClanMembershipPeriod.user_id == member.user_id,
                ClanMembershipPeriod.ended_at.is_(None),
            )
            .first()
        )
        if active:
            if active.clan_id != member.clan_id:
                raise ValueError("У пользователя уже есть активный период членства")
            return active

        period = ClanMembershipPeriod(
            user_id=member.user_id,
            clan_id=member.clan_id,
            started_at=as_utc(started_at or member.joined_at) or utc_now(),
            started_reason=reason,
        )
        db.add(period)
        PreseasonService().capture_candidates(db, now=utc_now())
        db.commit()
        db.refresh(period)
        # Право первых шести фиксируется при вступлении, а не при открытии страницы.
        PreseasonService().finish_qualification(db)
        return period

    def end(
        self,
        db: Session,
        member: ClanMember,
        *,
        reason: str,
        ended_at: datetime | None = None,
    ) -> ClanMembershipPeriod:
        from app.services.preseason_service import PreseasonService
        PreseasonService().lock_rosters(db)
        period = (
            db.query(ClanMembershipPeriod)
            .filter(
                ClanMembershipPeriod.user_id == member.user_id,
                ClanMembershipPeriod.clan_id == member.clan_id,
                ClanMembershipPeriod.ended_at.is_(None),
            )
            .first()
        )
        if period is None:
            period = ClanMembershipPeriod(
                user_id=member.user_id,
                clan_id=member.clan_id,
                started_at=as_utc(member.joined_at) or utc_now(),
                started_reason="legacy_backfill",
            )
            db.add(period)

        period.ended_at = as_utc(ended_at) or utc_now()
        if as_utc(period.started_at) > as_utc(period.ended_at):
            period.started_at = period.ended_at
        period.ended_reason = reason
        PreseasonService().capture_candidates(db, now=utc_now())
        db.commit()
        db.refresh(period)
        return period

    def clan_ids_at(
        self,
        db: Session,
        user_id: int,
        occurred_at: datetime,
    ) -> set[int]:
        occurred_at = as_utc(occurred_at)
        periods = (
            db.query(ClanMembershipPeriod)
            .filter(ClanMembershipPeriod.user_id == user_id)
            .all()
        )
        matching = {
            period.clan_id
            for period in periods
            if as_utc(period.started_at) <= occurred_at
            and (
                period.ended_at is None
                or occurred_at < as_utc(period.ended_at)
            )
        }
        if matching or periods:
            return matching

        # Совместимость с тестами и старыми базами до миграции истории членства.
        current_memberships = (
            db.query(ClanMember)
            .filter(ClanMember.user_id == user_id)
            .all()
        )
        return {
            member.clan_id
            for member in current_memberships
            if member.joined_at is None or as_utc(member.joined_at) <= occurred_at
        }
