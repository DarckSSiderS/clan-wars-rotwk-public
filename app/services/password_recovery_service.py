import hashlib
import hmac
import secrets
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from urllib.parse import urlencode

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import get_password_hash
from app.core.time import as_utc, utc_now
from app.models.password_recovery import PasswordRecoveryToken
from app.models.user import User


GENERIC_REQUEST_MESSAGE = (
    "Если аккаунт с таким адресом существует, письмо со ссылкой уже отправлено."
)


class PasswordRecoveryDelivery:
    def is_configured(self) -> bool:
        return bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL)

    def send(self, *, recipient: str, token: str, language: str) -> None:
        query = urlencode({"token": token})
        link = f"{settings.PASSWORD_RECOVERY_SITE_URL.rstrip('/')}/recover?{query}"
        subject = "Восстановление доступа middlewar.ru"
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.SMTP_FROM_EMAIL
        message["To"] = recipient
        message.set_content(
            "Вы запросили смену пароля middlewar.ru.\n\n"
            f"Ссылка действует {settings.PASSWORD_RECOVERY_TTL_MINUTES} минут:\n{link}\n\n"
            "Если это были не вы, просто проигнорируйте письмо."
        )

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            if settings.SMTP_USERNAME:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)


class PasswordRecoveryService:
    WINDOW_MINUTES = 15
    MAX_REQUESTS_PER_IP = 5
    MAX_REQUESTS_PER_EMAIL = 3

    def __init__(self, delivery: PasswordRecoveryDelivery | None = None):
        self.delivery = delivery or PasswordRecoveryDelivery()

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _email_hash(email: str) -> str:
        normalized = email.strip().casefold().encode("utf-8")
        return hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            normalized,
            hashlib.sha256,
        ).hexdigest()

    def request(self, db: Session, *, email: str, client_ip: str) -> str:
        if not self.delivery.is_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Почтовая доставка пока не настроена.",
            )

        normalized_email = email.strip().casefold()
        email_hash = self._email_hash(normalized_email)
        safe_ip = (client_ip or "unknown")[:64]
        cutoff = utc_now() - timedelta(minutes=self.WINDOW_MINUTES)

        ip_count = db.query(func.count(PasswordRecoveryToken.id)).filter(
            PasswordRecoveryToken.created_ip == safe_ip,
            PasswordRecoveryToken.created_at >= cutoff,
        ).scalar() or 0
        email_count = db.query(func.count(PasswordRecoveryToken.id)).filter(
            PasswordRecoveryToken.email_hash == email_hash,
            PasswordRecoveryToken.created_at >= cutoff,
        ).scalar() or 0
        if ip_count >= self.MAX_REQUESTS_PER_IP or email_count >= self.MAX_REQUESTS_PER_EMAIL:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много запросов. Повторите позже.",
            )

        user = db.query(User).filter(func.lower(User.email) == normalized_email).first()
        recovery = PasswordRecoveryToken(
            user_id=user.id if user and user.is_active and user.is_claimed else None,
            email_hash=email_hash,
            created_ip=safe_ip,
        )
        token = None
        if recovery.user_id is not None:
            token = secrets.token_urlsafe(32)
            recovery.token_hash = self._token_hash(token)
            recovery.expires_at = utc_now() + timedelta(
                minutes=settings.PASSWORD_RECOVERY_TTL_MINUTES
            )
        db.add(recovery)
        db.commit()

        if token is not None:
            try:
                self.delivery.send(
                    recipient=user.email,
                    token=token,
                    language=user.language or "ru",
                )
            except Exception as exc:
                db.delete(recovery)
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Не удалось отправить письмо. Повторите позже.",
                ) from exc
        return GENERIC_REQUEST_MESSAGE

    def confirm(self, db: Session, *, token: str, password: str) -> None:
        token_hash = self._token_hash(token)
        recovery = db.query(PasswordRecoveryToken).filter(
            PasswordRecoveryToken.token_hash == token_hash,
        ).first()
        now = utc_now()
        if (
            recovery is None
            or recovery.user_id is None
            or recovery.used_at is not None
            or recovery.expires_at is None
            or as_utc(recovery.expires_at) <= now
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ссылка недействительна или уже истекла.",
            )

        user = db.query(User).filter(User.id == recovery.user_id).first()
        if user is None or not user.is_active or not user.is_claimed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ссылка недействительна или уже истекла.",
            )

        user.hashed_password = get_password_hash(password)
        user.auth_version = int(user.auth_version or 0) + 1
        db.query(PasswordRecoveryToken).filter(
            PasswordRecoveryToken.user_id == user.id,
            PasswordRecoveryToken.used_at.is_(None),
        ).update({PasswordRecoveryToken.used_at: now}, synchronize_session=False)
        db.commit()
