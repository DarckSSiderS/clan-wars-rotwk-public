from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.external_identity import ExternalPlayerAlias, ExternalPlayerIdentity
from app.models.user import User
from app.services.operation_service import AdminAuditService


class AdminIdentityBindingService:
    SOURCE = "bfmeladder"

    def bind(
        self,
        db: Session,
        *,
        target_user: User,
        arena_nickname: str,
        actor: User,
        reason: str,
    ) -> ExternalPlayerIdentity:
        nickname = str(arena_nickname or "").strip()
        clean_reason = str(reason or "").strip()
        if not nickname or len(nickname) > 120:
            raise ValueError("Ник BFME Arena должен содержать от 1 до 120 символов")
        if len(clean_reason) < 3:
            raise ValueError("Причина должна содержать не меньше трёх символов")
        if not target_user.is_claimed:
            raise ValueError("Перепривязать ник можно только зарегистрированному аккаунту")
        from app.services.preseason_service import PreseasonService
        PreseasonService().lock_rosters(db)

        target = (
            db.query(User)
            .filter(User.id == target_user.id)
            .with_for_update()
            .first()
        )
        identity = (
            db.query(ExternalPlayerIdentity)
            .join(ExternalPlayerAlias)
            .filter(
                ExternalPlayerIdentity.source == self.SOURCE,
                func.lower(ExternalPlayerAlias.nickname) == nickname.lower(),
            )
            .order_by(ExternalPlayerAlias.last_seen_at.desc())
            .with_for_update()
            .first()
        )
        if identity is None:
            raise ValueError("Профиль с таким ником не найден среди импортированных матчей")

        source_user = (
            db.query(User)
            .filter(User.id == identity.user_id)
            .with_for_update()
            .first()
        )
        if source_user.id != target.id and source_user.is_claimed:
            raise ValueError("Этот ник BFME Arena уже привязан к другому зарегистрированному аккаунту")

        target_identity = (
            db.query(ExternalPlayerIdentity)
            .filter(
                ExternalPlayerIdentity.user_id == target.id,
                ExternalPlayerIdentity.source == self.SOURCE,
            )
            .with_for_update()
            .first()
        )
        if target_identity is not None and target_identity.id != identity.id:
            raise ValueError(
                "У пользователя уже есть другой UUID BFME Arena; автоматическое объединение запрещено"
            )

        before = {
            "username": target.username,
            "display_name": target.display_name,
            "identity_user_id": identity.user_id,
            "external_uuid": identity.external_uuid,
            "arena_nickname": identity.current_nickname,
        }
        if source_user.id != target.id:
            identity.user_id = target.id
            source_user.username = f"arena-merged-{source_user.id}"
            source_user.display_name = None
            source_user.is_active = False

        now = utc_now()
        identity.current_nickname = nickname
        identity.verification_status = "verified"
        identity.claimed_at = identity.claimed_at or now
        identity.verified_at = now
        identity.last_seen_at = now
        target.display_name = nickname

        alias = (
            db.query(ExternalPlayerAlias)
            .filter(
                ExternalPlayerAlias.identity_id == identity.id,
                func.lower(ExternalPlayerAlias.nickname) == nickname.lower(),
            )
            .first()
        )
        if alias is None:
            db.add(ExternalPlayerAlias(identity_id=identity.id, nickname=nickname))
        else:
            alias.last_seen_at = now

        AdminAuditService().record(
            db,
            actor_user_id=actor.id,
            action="arena_identity_rebound",
            entity_type="user",
            entity_id=target.id,
            before_data=before,
            after_data={
                "username": target.username,
                "display_name": nickname,
                "identity_user_id": target.id,
                "external_uuid": identity.external_uuid,
                "arena_nickname": nickname,
            },
            reason=clean_reason,
        )
        PreseasonService().capture_candidates(db, now=now)
        db.commit()
        PreseasonService().finish_qualification(db)
        db.refresh(identity)
        return identity
