from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.external_identity import ExternalPlayerAlias, ExternalPlayerIdentity
from app.models.user import User
from app.services.operation_service import AdminAuditService


class ExternalIdentityService:
    SOURCE = "bfmeladder"

    def uuid_for_known_nickname(self, db: Session, nickname: str) -> Optional[str]:
        """Legacy sources omit UUIDs; only use an unambiguous recorded identity."""
        name = str(nickname or '').strip().lower()
        rows = (db.query(ExternalPlayerIdentity.external_uuid)
                .outerjoin(ExternalPlayerAlias)
                .filter(ExternalPlayerIdentity.source == self.SOURCE, or_(
                    func.lower(func.trim(ExternalPlayerIdentity.current_nickname)) == name,
                    func.lower(func.trim(ExternalPlayerAlias.nickname)) == name,
                )).distinct().all())
        return rows[0][0] if name and len(rows) == 1 else None

    def get_by_uuid(
        self,
        db: Session,
        external_uuid: str,
        source: str = SOURCE,
    ) -> Optional[ExternalPlayerIdentity]:
        external_uuid = str(external_uuid or "").strip()
        if not external_uuid:
            return None
        return (
            db.query(ExternalPlayerIdentity)
            .filter(
                ExternalPlayerIdentity.source == source,
                ExternalPlayerIdentity.external_uuid == external_uuid,
            )
            .first()
        )

    def get_by_nickname(
        self,
        db: Session,
        nickname: str,
        source: str = SOURCE,
    ) -> Optional[ExternalPlayerIdentity]:
        nickname = str(nickname or "").strip()
        if not nickname:
            return None
        return (
            db.query(ExternalPlayerIdentity)
            .outerjoin(ExternalPlayerAlias)
            .filter(
                ExternalPlayerIdentity.source == source,
                or_(func.lower(func.trim(ExternalPlayerAlias.nickname)) == nickname.lower(),
                    func.lower(func.trim(ExternalPlayerIdentity.current_nickname)) == nickname.lower()),
            )
            .order_by(
                (func.lower(ExternalPlayerIdentity.current_nickname) == nickname.lower()).desc(),
                (ExternalPlayerIdentity.verification_status == "verified").desc(),
                ExternalPlayerAlias.last_seen_at.desc(),
            )
            .first()
        )

    def observe(
        self,
        db: Session,
        user: User,
        external_uuid: str,
        nickname: str,
        source: str = SOURCE,
    ) -> ExternalPlayerIdentity:
        external_uuid = str(external_uuid or "").strip()
        nickname = str(nickname or "").strip()
        if not external_uuid or not nickname:
            raise ValueError("Для внешней личности нужны UUID и ник")

        now = utc_now()
        identity = self.get_by_uuid(db, external_uuid, source)
        if identity is None:
            identity = ExternalPlayerIdentity(
                user_id=user.id,
                source=source,
                external_uuid=external_uuid,
                current_nickname=nickname,
                verification_status="pending" if user.is_claimed else "unverified",
                claimed_at=now if user.is_claimed else None,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(identity)
            db.flush()
        else:
            # Historical replays must not overwrite the name confirmed by OAuth.
            if identity.verification_status != "verified":
                identity.current_nickname = nickname
            identity.last_seen_at = now

        alias = (
            db.query(ExternalPlayerAlias)
            .filter(
                ExternalPlayerAlias.identity_id == identity.id,
                ExternalPlayerAlias.nickname == nickname,
            )
            .first()
        )
        if alias is None:
            db.add(
                ExternalPlayerAlias(
                    identity_id=identity.id,
                    nickname=nickname,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        else:
            alias.last_seen_at = now

        from app.services.profile_reconciliation_service import ProfileReconciliationService
        ProfileReconciliationService().reconcile(db, identity)
        db.commit()
        db.refresh(identity)
        return identity

    def mark_claimed(self, db: Session, user: User) -> None:
        now = utc_now()
        changed = False
        for identity in user.external_identities:
            if identity.verification_status == "unverified":
                identity.verification_status = "pending"
            if identity.claimed_at is None:
                identity.claimed_at = now
            changed = True
        if changed:
            db.commit()

    def status_for_user(self, user: User) -> Optional[str]:
        statuses = {
            identity.verification_status
            for identity in user.external_identities
        }
        for status in ("verified", "pending", "unverified"):
            if status in statuses:
                return status
        return None

    def primary_for_user(
        self,
        db: Session,
        user_id: int,
    ) -> Optional[ExternalPlayerIdentity]:
        return (
            db.query(ExternalPlayerIdentity)
            .filter(ExternalPlayerIdentity.user_id == user_id)
            .order_by(ExternalPlayerIdentity.last_seen_at.desc())
            .first()
        )

    def names_for_user(self, db: Session, user_id: int) -> set[str]:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            return set()
        names = {user.username}
        if user.display_name:
            names.add(user.display_name)
        identities = (
            db.query(ExternalPlayerIdentity)
            .filter(ExternalPlayerIdentity.user_id == user.id)
            .all()
        )
        identity_ids = [identity.id for identity in identities]
        names.update(identity.current_nickname for identity in identities if identity.current_nickname)
        if identity_ids:
            names.update(
                nickname
                for (nickname,) in db.query(ExternalPlayerAlias.nickname)
                .filter(ExternalPlayerAlias.identity_id.in_(identity_ids))
                .all()
                if nickname
            )
        return names

    def request_verification(
        self,
        db: Session,
        user: User,
    ) -> ExternalPlayerIdentity:
        identity = self.primary_for_user(db, user.id)
        if identity is None:
            raise ValueError(
                "Сначала сыграйте матч, чтобы сайт получил UUID игрового аккаунта"
            )
        if not user.is_claimed:
            raise ValueError("Сначала зарегистрируйте игровой профиль")
        if identity.verification_status != "verified":
            identity.verification_status = "pending"
            if identity.claimed_at is None:
                identity.claimed_at = utc_now()
            identity.verified_at = None
            db.commit()
            db.refresh(identity)
        return identity

    def review_verification(
        self,
        db: Session,
        *,
        target_user: User,
        reviewer: User,
        decision: str,
        reason: str,
    ) -> ExternalPlayerIdentity:
        if decision not in {"approve", "reject"}:
            raise ValueError("Неизвестное решение проверки")
        from app.services.preseason_service import PreseasonService
        PreseasonService().lock_rosters(db)

        identity = self.primary_for_user(db, target_user.id)
        if identity is None:
            raise ValueError("У пользователя нет внешнего игрового UUID")
        if identity.verification_status != "pending":
            raise ValueError("На проверке нет активной заявки")

        before_status = identity.verification_status
        identity.verification_status = (
            "verified" if decision == "approve" else "unverified"
        )
        identity.verified_at = utc_now() if decision == "approve" else None
        AdminAuditService().record(
            db,
            actor_user_id=reviewer.id,
            action=f"external_identity_{identity.verification_status}",
            entity_type="external_player_identity",
            entity_id=identity.id,
            before_data={
                "status": before_status,
                "user_id": target_user.id,
                "external_uuid": identity.external_uuid,
            },
            after_data={
                "status": identity.verification_status,
                "user_id": target_user.id,
                "nickname": identity.current_nickname,
            },
            reason=reason,
        )
        PreseasonService().capture_candidates(db, now=utc_now())
        db.commit()
        PreseasonService().finish_qualification(db)
        db.refresh(identity)
        return identity
