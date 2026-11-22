from fastapi import Response

from app.config import settings


def set_session_cookie(response: Response, token: str) -> None:
    """Устанавливает защищённую cookie серверной сессии."""
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=int(settings.SESSION_TTL_SECONDS),
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    """Удаляет cookie серверной сессии с теми же атрибутами."""
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value="",
        max_age=0,
        expires=0,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
