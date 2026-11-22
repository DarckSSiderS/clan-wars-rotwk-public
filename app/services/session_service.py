from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets

from sqlalchemy import update
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models.auth_session import SecurityAuditEvent, UserSession
from app.models.user import User


TOUCH_INTERVAL = timedelta(minutes=5)


@dataclass(frozen=True)
class SessionIssue:
    token: str
    expires_at: datetime


class InvalidSession(Exception):
    """Сессия отсутствует, недействительна или больше не разрешена."""


class SessionService:
    """Управляет непрозрачными серверными сессиями пользователей."""

    def issue(
        self,
        db: Session,
        user: User,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        impersonated_by_user_id: int | None = None,
        now: datetime | None = None,
        commit: bool = True,
    ) -> SessionIssue:
        issued_at = self._as_utc(now or datetime.now(timezone.utc))
        expires_at = issued_at + timedelta(
            seconds=settings.SESSION_TTL_SECONDS
        )
        token = secrets.token_urlsafe(48)
        user_session = UserSession(
            user_id=user.id,
            token_hash=self._hash_token(token),
            expires_at=expires_at,
            is_impersonation=impersonated_by_user_id is not None,
            impersonated_by_user_id=impersonated_by_user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=issued_at,
            last_seen_at=issued_at,
        )
        db.add(user_session)
        db.add(
            SecurityAuditEvent(
                user_id=user.id,
                actor_user_id=impersonated_by_user_id or user.id,
                event_type="session_created",
                ip_address=ip_address,
                event_metadata={
                    "impersonation": impersonated_by_user_id is not None
                },
            )
        )
        try:
            if commit:
                db.commit()
            else:
                db.flush()
        except Exception:
            if commit:
                db.rollback()
            raise
        return SessionIssue(token=token, expires_at=expires_at)

    def resolve(
        self,
        db: Session,
        token: str,
        *,
        now: datetime | None = None,
        touch: bool = True,
    ) -> UserSession:
        if not isinstance(token, str) or not token:
            raise InvalidSession()

        resolved_at = self._as_utc(now or datetime.now(timezone.utc))
        token_hash = self._hash_token(token)
        user_session = (
            db.query(UserSession)
            .options(
                joinedload(UserSession.user).joinedload(User.role),
                joinedload(UserSession.impersonated_by_user).joinedload(
                    User.role
                ),
            )
            .filter(UserSession.token_hash == token_hash)
            .first()
        )
        if (
            user_session is None
            or not hmac.compare_digest(user_session.token_hash, token_hash)
            or user_session.revoked_at is not None
            or self._as_utc(user_session.expires_at) <= resolved_at
            or user_session.user is None
        ):
            raise InvalidSession()

        actor = user_session.impersonated_by_user
        has_actor_reference = user_session.impersonated_by_user_id is not None
        is_admin_impersonation = user_session.is_impersonation
        if is_admin_impersonation != has_actor_reference or (
            is_admin_impersonation
            and (actor is None or not self._is_active_admin(actor))
        ):
            self._revoke_invalid_impersonation(
                db,
                user_session,
                now=resolved_at,
            )
        if not user_session.user.is_active and not is_admin_impersonation:
            raise InvalidSession()

        user_session.user.__dict__.pop("_is_admin_impersonation", None)
        user_session.user.__dict__.pop("_impersonated_by_username", None)
        if is_admin_impersonation:
            user_session.user._is_admin_impersonation = True
            user_session.user._impersonated_by_username = actor.username

        if touch:
            self.touch(db, user_session, now=resolved_at)
        return user_session

    def touch(
        self,
        db: Session,
        user_session: UserSession,
        *,
        now: datetime | None = None,
    ) -> bool:
        touched_at = self._as_utc(now or datetime.now(timezone.utc))
        last_seen_at = self._as_utc(user_session.last_seen_at)
        if touched_at - last_seen_at < TOUCH_INTERVAL:
            return False
        cutoff = touched_at - TOUCH_INTERVAL
        # База повторно проверяет условие после конкурентной блокировки строки.
        result = db.execute(
            update(UserSession)
            .where(
                UserSession.id == user_session.id,
                UserSession.last_seen_at <= cutoff,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > touched_at,
            )
            .values(last_seen_at=touched_at)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        return result.rowcount == 1

    def revoke(
        self,
        db: Session,
        token: str,
        *,
        now: datetime | None = None,
        commit: bool = True,
    ) -> bool:
        if not isinstance(token, str) or not token:
            return False
        token_hash = self._hash_token(token)
        user_session = (
            db.query(UserSession)
            .filter(UserSession.token_hash == token_hash)
            .with_for_update()
            .first()
        )
        if (
            user_session is None
            or not hmac.compare_digest(user_session.token_hash, token_hash)
            or user_session.revoked_at is not None
        ):
            return False

        revoked_at = self._as_utc(now or datetime.now(timezone.utc))
        user_session.revoked_at = revoked_at
        db.add(
            SecurityAuditEvent(
                user_id=user_session.user_id,
                actor_user_id=(user_session.impersonated_by_user_id)
                or user_session.user_id,
                event_type="session_revoked",
                ip_address=user_session.ip_address,
                event_metadata={
                    "impersonation": user_session.is_impersonation
                },
            )
        )
        try:
            if commit:
                db.commit()
            else:
                db.flush()
        except Exception:
            if commit:
                db.rollback()
            raise
        return True

    def rotate(
        self,
        db: Session,
        current_token: str,
        user: User,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        impersonated_by_user_id: int | None = None,
        now: datetime | None = None,
        commit: bool = True,
    ) -> SessionIssue:
        """Атомарно отзывает текущую сессию и выпускает замену."""
        try:
            if not self.revoke(
                db,
                current_token,
                now=now,
                commit=False,
            ):
                raise InvalidSession()
            issue = self.issue(
                db,
                user,
                ip_address=ip_address,
                user_agent=user_agent,
                impersonated_by_user_id=impersonated_by_user_id,
                now=now,
                commit=False,
            )
            if commit:
                db.commit()
            return issue
        except Exception:
            if commit:
                db.rollback()
            raise

    def revoke_all(
        self,
        db: Session,
        user_id: int,
        *,
        except_token: str | None = None,
        now: datetime | None = None,
    ) -> int:
        revoked_at = self._as_utc(now or datetime.now(timezone.utc))
        query = db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
        if except_token:
            query = query.filter(
                UserSession.token_hash != self._hash_token(except_token)
            )
        sessions = query.with_for_update().all()
        for user_session in sessions:
            user_session.revoked_at = revoked_at

        db.add(
            SecurityAuditEvent(
                user_id=user_id,
                actor_user_id=user_id,
                event_type="sessions_revoked_all",
                event_metadata={
                    "revoked_count": len(sessions),
                    "kept_current": except_token is not None,
                },
            )
        )
        db.commit()
        return len(sessions)

    @staticmethod
    def _is_active_admin(user: User) -> bool:
        return bool(
            user.is_active
            and user.role is not None
            and user.role.name == "admin"
        )

    @staticmethod
    def _revoke_invalid_impersonation(
        db: Session,
        user_session: UserSession,
        *,
        now: datetime,
    ) -> None:
        """Отзывает сессию с недостоверным источником подмены."""
        user_session.revoked_at = now
        db.add(
            SecurityAuditEvent(
                user_id=user_session.user_id,
                actor_user_id=None,
                event_type="session_revoked",
                ip_address=user_session.ip_address,
                event_metadata={
                    "impersonation": True,
                    "reason": "invalid_impersonation_provenance",
                },
            )
        )
        db.commit()
        raise InvalidSession()

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
