from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
import unicodedata
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.config import settings
from app.models import OAuthLoginState


@dataclass(frozen=True)
class OAuthStateIssue:
    state: str
    flow_token: str
    authorize_params: dict[str, str]


class InvalidOAuthState(Exception):
    pass


class OAuthStateService:
    def issue(
        self,
        db: Session,
        return_to: str,
        now: datetime | None = None,
    ) -> OAuthStateIssue:
        now = self._as_utc(now or datetime.now(timezone.utc))
        state = secrets.token_urlsafe(32)
        flow_token = secrets.token_urlsafe(32)
        db.add(
            OAuthLoginState(
                state_hash=self._hash_token(state),
                flow_hash=self._hash_token(flow_token),
                return_to=self._safe_return_to(return_to),
                expires_at=now + timedelta(seconds=settings.BFME_OAUTH_STATE_TTL_SECONDS),
            )
        )
        db.commit()
        return OAuthStateIssue(
            state=state,
            flow_token=flow_token,
            authorize_params={
                "client_id": settings.BFME_OAUTH_CLIENT_ID,
                "redirect_uri": settings.BFME_OAUTH_REDIRECT_URI,
                "state": state,
            },
        )

    def consume(
        self,
        db: Session,
        state: str,
        flow_token: str,
        now: datetime | None = None,
    ) -> OAuthLoginState:
        if not isinstance(state, str) or not isinstance(flow_token, str):
            raise InvalidOAuthState()

        now = self._as_utc(now or datetime.now(timezone.utc))
        state_hash = self._hash_token(state)
        flow_hash = self._hash_token(flow_token)
        login_state = (
            db.query(OAuthLoginState)
            .filter(OAuthLoginState.state_hash == state_hash)
            .with_for_update()
            .first()
        )
        if (
            login_state is None
            or not hmac.compare_digest(login_state.state_hash, state_hash)
            or not hmac.compare_digest(login_state.flow_hash, flow_hash)
            or login_state.consumed_at is not None
            or self._as_utc(login_state.expires_at) <= self._as_utc(now)
        ):
            raise InvalidOAuthState()

        login_state.consumed_at = self._as_utc(now)
        db.commit()
        return login_state

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _safe_return_to(return_to: str) -> str:
        if not isinstance(return_to, str) or not return_to.startswith("/"):
            return "/"
        if return_to.startswith("//") or "\\" in return_to:
            return "/"
        if any(unicodedata.category(char) == "Cc" for char in return_to):
            return "/"
        try:
            parsed = urlsplit(return_to)
        except ValueError:
            return "/"
        if parsed.scheme or parsed.netloc:
            return "/"
        return return_to
