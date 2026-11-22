from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.user import User
from app.core.security import verify_password
from app.config import settings
from app.models.auth_session import UserSession
from app.services.session_service import InvalidSession, SessionService


def authenticate_user(
    db: Session,
    username: str,
    password: str,
) -> Optional[User]:
    """Аутентифицирует пользователя"""
    user = (
        db.query(User)
        .options(joinedload(User.role))
        .filter(User.username == username)
        .first()
    )
    if not user or not user.is_claimed or not user.hashed_password:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def get_current_session(
    request: Request,
    db: Session = Depends(get_db),
) -> UserSession:
    """Получает текущую серверную cookie-сессию."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось проверить учетные данные",
        headers={},
    )
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    try:
        return SessionService().resolve(db, token)
    except InvalidSession as exc:
        raise credentials_exception from exc


async def get_current_user(
    current_session: UserSession = Depends(get_current_session),
) -> User:
    """Получает текущего пользователя только из серверной cookie-сессии."""
    return current_session.user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Получает активного пользователя"""
    if not current_user.is_active and not getattr(
        current_user,
        "_is_admin_impersonation",
        False,
    ):
        raise HTTPException(status_code=400, detail="Неактивный пользователь")
    return current_user


async def get_onboarded_active_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Проверяет завершение обязательной первичной настройки."""
    if current_user.onboarding_completed_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="onboarding_required",
        )
    return current_user

def get_current_admin_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Проверяет, что текущий пользователь является администратором"""
    if not current_user.role or current_user.role.name != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав. Требуется роль администратора.",
        )
    return current_user
