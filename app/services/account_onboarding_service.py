from datetime import datetime
from hashlib import sha256

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import get_password_hash
from app.core.time import utc_now
from app.models.auth_session import SecurityAuditEvent
from app.models.external_identity import (
    ExternalPlayerAlias,
    ExternalPlayerIdentity,
)
from app.models.role import Role
from app.models.user import User
from app.services.external_identity_service import ExternalIdentityService


HISTORY_MODE_NEW = "new"
HISTORY_MODE_FULL = "full"


class AccountIdentityConflict(Exception):
    pass


class OnboardingValidationError(Exception):
    pass


class AccountOnboardingService:
    SOURCE = "bfmeladder"
    HISTORY_MODES = {HISTORY_MODE_NEW, HISTORY_MODE_FULL}
    LANGUAGES = {"ru", "en", "de"}

    def __init__(self) -> None:
        self.identity_service = ExternalIdentityService()

    def get_or_create_arena_user(
        self,
        db: Session,
        external_uuid: str,
        display_name: str,
    ) -> tuple[User, bool]:
        clean_uuid = str(external_uuid or "").strip()
        clean_name = str(display_name or "").strip()
        self._validate_identity(clean_uuid, clean_name)
        from app.services.preseason_service import PreseasonService
        PreseasonService().lock_rosters(db)

        identity = self.identity_service.get_by_uuid(
            db,
            clean_uuid,
            self.SOURCE,
        )
        if identity is not None:
            return self._claim_existing_identity(
                db,
                identity,
                clean_name,
            ), False

        admin_role = self._primary_admin_role(db, clean_uuid)
        username = self._available_username(db, clean_name, clean_uuid)
        now = utc_now()
        user = User(
            username=username,
            display_name=clean_name,
            email=None,
            hashed_password=None,
            is_active=True,
            is_claimed=True,
        )
        if admin_role is not None:
            user.role = admin_role
        identity = ExternalPlayerIdentity(
            user=user,
            source=self.SOURCE,
            external_uuid=clean_uuid,
            current_nickname=clean_name,
            verification_status="verified",
            claimed_at=now,
            verified_at=now,
            first_seen_at=now,
            last_seen_at=now,
        )
        identity.aliases.append(
            ExternalPlayerAlias(
                nickname=clean_name,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        db.add(user)
        try:
            from app.services.profile_reconciliation_service import ProfileReconciliationService
            db.flush()
            ProfileReconciliationService().reconcile(db, identity)
            from app.services.preseason_service import PreseasonService
            PreseasonService().capture_candidates(db, now=now)
            db.commit()
            PreseasonService().finish_qualification(db)
        except IntegrityError as exc:
            db.rollback()
            concurrent_identity = self.identity_service.get_by_uuid(
                db,
                clean_uuid,
                self.SOURCE,
            )
            if concurrent_identity is not None:
                return self._claim_existing_identity(
                    db,
                    concurrent_identity,
                    clean_name,
                ), False
            raise AccountIdentityConflict(
                "Не удалось однозначно создать аккаунт BFME Arena"
            ) from exc
        db.refresh(user)
        return user, True

    def complete_onboarding(
        self,
        db: Session,
        user: User,
        history_mode: str,
        language: str,
        accepted_rules: bool,
        password: str | None = None,
        now: datetime | None = None,
        commit: bool = True,
    ) -> User:
        current_user = (
            db.query(User)
            .filter(User.id == user.id)
            .populate_existing()
            .with_for_update()
            .one_or_none()
        )
        if current_user is None:
            raise OnboardingValidationError("Пользователь не найден")
        if current_user.onboarding_completed_at is not None:
            raise OnboardingValidationError(
                "Первичная настройка уже завершена"
            )
        if accepted_rules is not True:
            raise OnboardingValidationError(
                "Необходимо принять правила проекта"
            )
        if history_mode not in self.HISTORY_MODES:
            raise OnboardingValidationError("Неизвестный режим истории")
        if language not in self.LANGUAGES:
            raise OnboardingValidationError("Неподдерживаемый язык")

        normalized_password = self._normalize_password(password)
        hashed_password = (
            get_password_hash(normalized_password)
            if normalized_password is not None
            else None
        )
        completed_at = now or utc_now()
        current_user.onboarding_completed_at = completed_at
        current_user.statistics_started_at = (
            completed_at if history_mode == HISTORY_MODE_NEW else None
        )
        current_user.history_mode = history_mode
        current_user.language = language
        current_user.hashed_password = hashed_password
        db.add(
            SecurityAuditEvent(
                user_id=current_user.id,
                event_type="onboarding_completed",
                event_metadata={
                    "history_mode": history_mode,
                    "password_enabled": normalized_password is not None,
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
        db.refresh(current_user)
        return current_user

    def _claim_existing_identity(
        self,
        db: Session,
        identity: ExternalPlayerIdentity,
        display_name: str,
        expected_aliases: set[str] | None = None,
        retry_on_integrity_error: bool = True,
    ) -> User:
        external_uuid = identity.external_uuid
        from app.services.preseason_service import PreseasonService
        PreseasonService().lock_rosters(db)
        if expected_aliases is None:
            expected_aliases = {
                identity.current_nickname,
                display_name,
            }
        admin_role = self._primary_admin_role(db, external_uuid)
        user = identity.user
        now = utc_now()
        old_nickname = identity.current_nickname
        was_claimed = user.is_claimed
        user.display_name = display_name
        user.is_claimed = True
        if not was_claimed:
            user.is_active = True
        identity.current_nickname = display_name
        identity.verification_status = "verified"
        identity.claimed_at = identity.claimed_at or now
        identity.verified_at = now
        identity.last_seen_at = now
        self._record_alias(db, identity, old_nickname, now)
        self._record_alias(db, identity, display_name, now)

        if admin_role is not None:
            user.role = admin_role
        try:
            from app.services.profile_reconciliation_service import ProfileReconciliationService
            ProfileReconciliationService().reconcile(db, identity)
            from app.services.preseason_service import PreseasonService
            PreseasonService().capture_candidates(db, now=now)
            db.commit()
            PreseasonService().finish_qualification(db)
        except IntegrityError as exc:
            db.rollback()
            current = self.identity_service.get_by_uuid(
                db,
                external_uuid,
                self.SOURCE,
            )
            if current is not None and retry_on_integrity_error:
                return self._claim_existing_identity(
                    db,
                    current,
                    display_name,
                    expected_aliases=expected_aliases,
                    retry_on_integrity_error=False,
                )
            raise AccountIdentityConflict(
                "Не удалось однозначно обновить аккаунт BFME Arena"
            ) from exc
        return self._verified_claim_user(
            db,
            external_uuid,
            display_name,
            expected_aliases,
        )

    def _verified_claim_user(
        self,
        db: Session,
        external_uuid: str,
        display_name: str,
        expected_aliases: set[str],
    ) -> User:
        identity = self.identity_service.get_by_uuid(
            db,
            external_uuid,
            self.SOURCE,
        )
        if identity is None:
            raise AccountIdentityConflict(
                "UUID BFME Arena исчез после сохранения аккаунта"
            )
        db.refresh(identity)
        aliases = {
            nickname
            for (nickname,) in db.query(ExternalPlayerAlias.nickname)
            .filter(ExternalPlayerAlias.identity_id == identity.id)
            .all()
        }
        if not (
            identity.user.is_claimed
            and identity.verification_status == "verified"
            and identity.claimed_at is not None
            and identity.verified_at is not None
            and identity.current_nickname == display_name
            and identity.user.display_name == display_name
            and expected_aliases <= aliases
        ):
            raise AccountIdentityConflict(
                "Аккаунт BFME Arena сохранен не полностью"
            )
        return identity.user

    def _record_alias(
        self,
        db: Session,
        identity: ExternalPlayerIdentity,
        nickname: str,
        now: datetime,
    ) -> None:
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

    def _available_username(
        self,
        db: Session,
        display_name: str,
        external_uuid: str,
    ) -> str:
        if not self._username_exists(db, display_name):
            return display_name

        digest = sha256(external_uuid.encode("utf-8")).hexdigest()
        for length in range(8, len(digest) + 1):
            candidate = f"{display_name}~{digest[:length]}"
            if not self._username_exists(db, candidate):
                return candidate

        counter = 2
        while self._username_exists(db, f"{display_name}~{digest}~{counter}"):
            counter += 1
        return f"{display_name}~{digest}~{counter}"

    @staticmethod
    def _username_exists(db: Session, username: str) -> bool:
        return (
            db.query(User.id).filter(User.username == username).first()
            is not None
        )

    @staticmethod
    def _validate_identity(external_uuid: str, display_name: str) -> None:
        if not 1 <= len(external_uuid) <= 80:
            raise OnboardingValidationError(
                "UUID BFME Arena должен содержать от 1 до 80 символов"
            )
        if not 1 <= len(display_name) <= 120:
            raise OnboardingValidationError(
                "Ник BFME Arena должен содержать от 1 до 120 символов"
            )

    @staticmethod
    def _normalize_password(password: str | None) -> str | None:
        if password is None or not password.strip():
            return None
        if not 10 <= len(password) <= 128:
            raise OnboardingValidationError(
                "Пароль должен содержать от 10 до 128 символов"
            )
        return password

    @staticmethod
    def _primary_admin_role(db: Session, external_uuid: str) -> Role | None:
        configured_uuid = settings.BFME_PRIMARY_ADMIN_UUID
        if not configured_uuid or external_uuid != configured_uuid:
            return None
        role = db.query(Role).filter(Role.name == "admin").first()
        if role is None:
            raise RuntimeError(
                "Для BFME_PRIMARY_ADMIN_UUID не настроена роль admin"
            )
        return role
