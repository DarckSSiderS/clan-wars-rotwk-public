import asyncio
import inspect
import math
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from urllib.parse import urlencode

import aiohttp


@dataclass(frozen=True)
class ArenaIdentity:
    uuid: str
    display_name: str


class ArenaOAuthUnavailable(Exception):
    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        status: int | None = None,
        reason: str | None = None,
    ):
        super().__init__(message)
        self.stage = stage
        self.status = status
        self.reason = reason


class ArenaOAuthRejected(Exception):
    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        status: int | None = None,
        provider_error: str | None = None,
    ):
        super().__init__(message)
        self.stage = stage
        self.status = status
        self.provider_error = provider_error


class BfmeOAuthService:
    def __init__(self, settings: Any, session_factory: Callable[[], Any] | None = None):
        self._settings = settings
        self._session_factory = session_factory

    def build_authorize_url(self, state: str) -> str:
        query = urlencode(
            {
                "client_id": self._settings.BFME_OAUTH_CLIENT_ID,
                "redirect_uri": self._settings.BFME_OAUTH_REDIRECT_URI,
                "state": state,
            }
        )
        return f"{self._settings.BFME_OAUTH_AUTHORIZE_URL}?{query}"

    async def exchange_code(self, code: str) -> str:
        try:
            return await self._with_session(lambda session: self._exchange(session, code))
        except (ArenaOAuthRejected, ArenaOAuthUnavailable):
            raise
        except (asyncio.TimeoutError, aiohttp.ClientError, ValueError, TypeError, KeyError):
            raise ArenaOAuthUnavailable(
                "Сервис Arena OAuth недоступен",
                stage="token",
                reason="transport",
            ) from None

    async def fetch_identity(self, access_token: str) -> ArenaIdentity:
        try:
            return await self._with_session(
                lambda session: self._fetch_identity(session, access_token)
            )
        except (ArenaOAuthRejected, ArenaOAuthUnavailable):
            raise
        except (asyncio.TimeoutError, aiohttp.ClientError, ValueError, TypeError, KeyError):
            raise ArenaOAuthUnavailable(
                "Сервис Arena OAuth недоступен",
                stage="identity",
                reason="transport",
            ) from None

    async def _with_session(self, operation: Callable[[Any], Awaitable[Any]]) -> Any:
        if self._session_factory is not None:
            session = self._session_factory()
            if inspect.isawaitable(session):
                session = await session
            return await operation(session)

        timeout = aiohttp.ClientTimeout(
            total=self._settings.BFME_OAUTH_HTTP_TIMEOUT_SECONDS
        )
        async with aiohttp.ClientSession(timeout=timeout) as session:
            return await operation(session)

    async def _exchange(self, session: Any, code: str) -> str:
        form = {
            "code": code,
            "redirect_url": self._settings.BFME_OAUTH_REDIRECT_URI,
            "redirect_uri": self._settings.BFME_OAUTH_REDIRECT_URI,
            "client_id": self._settings.BFME_OAUTH_CLIENT_ID,
            "client_secret": self._settings.BFME_OAUTH_CLIENT_SECRET,
            "grant_type": "authorization_code",
        }
        async with session.post(self._settings.BFME_OAUTH_TOKEN_URL, data=form) as response:
            payload = await self._response_payload(response, stage="token")
            self._raise_for_status(response.status, stage="token", payload=payload)
        try:
            return self._access_token_from_payload(payload)
        except ValueError as exc:
            raise ArenaOAuthUnavailable(
                "Сервис Arena OAuth вернул некорректный токен",
                stage="token",
                status=response.status,
                reason=f"payload_{exc}",
            ) from None

    async def _fetch_identity(self, session: Any, access_token: str) -> ArenaIdentity:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        async with session.get(
            self._settings.BFME_OAUTH_IDENTITY_URL, headers=headers
        ) as response:
            payload = await self._response_payload(response, stage="identity")
            self._raise_for_status(response.status, stage="identity", payload=payload)
        try:
            return self._identity_from_payload(payload)
        except ValueError as exc:
            raise ArenaOAuthUnavailable(
                "Сервис Arena OAuth вернул некорректный профиль",
                stage="identity",
                status=response.status,
                reason=f"payload_{exc}",
            ) from None

    @staticmethod
    async def _response_payload(response: Any, *, stage: str) -> Any:
        try:
            return await response.json()
        except (aiohttp.ContentTypeError, ValueError, TypeError):
            if 200 <= response.status < 300:
                raise ArenaOAuthUnavailable(
                    "Сервис Arena OAuth вернул не-JSON ответ",
                    stage=stage,
                    status=response.status,
                    reason="invalid_json",
                ) from None
            return None

    @staticmethod
    def _raise_for_status(status: int, *, stage: str, payload: Any) -> None:
        if status in {400, 401, 403}:
            provider_error = payload.get("error") if isinstance(payload, dict) else None
            if provider_error not in {
                "invalid_request",
                "invalid_client",
                "invalid_grant",
                "unauthorized_client",
                "unsupported_grant_type",
            }:
                provider_error = "other" if provider_error else None
            raise ArenaOAuthRejected(
                "Запрос Arena OAuth отклонён",
                stage=stage,
                status=status,
                provider_error=provider_error,
            )
        if not 200 <= status < 300:
            raise ArenaOAuthUnavailable(
                "Сервис Arena OAuth недоступен",
                stage=stage,
                status=status,
                reason="http",
            )

    @staticmethod
    def _access_token_from_payload(payload: Any) -> str:
        if not isinstance(payload, dict):
            raise ValueError("not_object")

        access_token = payload.get("access_token")
        token_type = payload.get("token_type")
        expires_in = payload.get("expires_in")
        scope = payload.get("scope")
        if not isinstance(access_token, str) or not access_token.strip():
            raise ValueError("access_token")
        if not isinstance(token_type, str) or token_type.casefold() != "bearer":
            raise ValueError("token_type")
        if (
            isinstance(expires_in, bool)
            or not isinstance(expires_in, (int, float))
            or not math.isfinite(expires_in)
            or expires_in <= 0
        ):
            raise ValueError("expires_in")
        if not isinstance(scope, str) or "identity" not in scope.split():
            raise ValueError("scope")
        return access_token

    @staticmethod
    def _identity_from_payload(payload: Any) -> ArenaIdentity:
        if not isinstance(payload, dict):
            raise ValueError("not_object")

        uuid = payload.get("uuid")
        display_name = payload.get("displayName")
        if (
            not isinstance(uuid, str)
            or not uuid.strip()
            or len(uuid) > 80
            or not isinstance(display_name, str)
        ):
            raise ValueError("uuid")
        display_name = display_name.strip()
        if not display_name or len(display_name) > 120:
            raise ValueError("display_name")
        return ArenaIdentity(uuid=uuid, display_name=display_name)
