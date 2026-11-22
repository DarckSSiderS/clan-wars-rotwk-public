from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import verify_password
from app.core.session_cookie import clear_session_cookie, set_session_cookie
from app.database import get_db
from app.models.auth_session import SecurityAuditEvent, UserSession
from app.models.external_identity import (
    ExternalPlayerIdentity,
    canonical_nickname_key,
)
from app.models.user import User
from app.schemas.oauth import (
    OnboardingRequest,
    PasswordLoginRequest,
    RevokeAllResponse,
    SessionUserSummary,
)
from app.schemas.auth import (
    PasswordRecoveryConfirm,
    PasswordRecoveryConfirmResult,
    PasswordRecoveryRequest,
    PasswordRecoveryRequestResult,
)
from app.services.account_onboarding_service import (
    AccountIdentityConflict,
    AccountOnboardingService,
    OnboardingValidationError,
)
from app.services.arena_match_backfill_service import ArenaMatchBackfillService
from app.services.bfme_oauth_service import (
    ArenaOAuthRejected,
    ArenaOAuthUnavailable,
    BfmeOAuthService,
)
from app.services.oauth_state_service import (
    InvalidOAuthState,
    OAuthStateService,
)
from app.services.operation_service import AdminAuditService
from app.services.password_recovery_service import PasswordRecoveryService
from app.services.session_service import InvalidSession, SessionService


DUMMY_PASSWORD_HASH = (
    "$bcrypt-sha256$v=2,t=2b,r=12$KcsmK6OtDAsB7vGVAMCQsO$"
    "jNMoEW5IdMa9MCZJlL5QJXvKUqN4FIG"
)


class OAuthAPIRoute(APIRoute):
    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def redacted_handler(request: Request):
            try:
                return await original_handler(request)
            except RequestValidationError as exc:
                safe_errors = []
                for error in exc.errors():
                    safe_error = dict(error)
                    if "password" in safe_error.get("loc", ()):
                        safe_error.pop("input", None)
                    safe_errors.append(safe_error)
                raise RequestValidationError(safe_errors, body=None) from exc

        return redacted_handler


router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
    route_class=OAuthAPIRoute,
)


def get_oauth_state_service() -> OAuthStateService:
    return OAuthStateService()


def get_bfme_oauth_service() -> BfmeOAuthService:
    return BfmeOAuthService(settings)


def get_session_service() -> SessionService:
    return SessionService()


def get_account_onboarding_service() -> AccountOnboardingService:
    return AccountOnboardingService()


def get_arena_match_backfill_service() -> ArenaMatchBackfillService:
    return ArenaMatchBackfillService()


def get_password_recovery_service() -> PasswordRecoveryService:
    return PasswordRecoveryService()


def _set_flow_cookie(response: Response, flow_token: str) -> None:
    response.set_cookie(
        key=settings.OAUTH_FLOW_COOKIE_NAME,
        value=flow_token,
        max_age=int(settings.BFME_OAUTH_STATE_TTL_SECONDS),
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def _clear_flow_cookie(response: Response) -> None:
    response.set_cookie(
        key=settings.OAUTH_FLOW_COOKIE_NAME,
        value="",
        max_age=0,
        expires=0,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def _request_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    return request.client.host[:64]


def _request_user_agent(request: Request) -> str | None:
    user_agent = request.headers.get("user-agent")
    return user_agent[:500] if user_agent else None


def _require_session(
    request: Request,
    db: Session = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
) -> UserSession:
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    try:
        return session_service.resolve(db, token)
    except InvalidSession as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_session"},
        ) from exc


def _session_summary(user) -> SessionUserSummary:
    summary = SessionUserSummary.model_validate(user)
    return summary.model_copy(
        update={
            "is_admin_impersonation": getattr(
                user,
                "_is_admin_impersonation",
                False,
            ),
            "impersonated_by_username": getattr(
                user,
                "_impersonated_by_username",
                None,
            ),
        }
    )


def _record_failed_login(
    db: Session,
    request: Request,
    event_type: str,
    reason: str,
    *,
    user_id: int | None = None,
) -> None:
    db.add(
        SecurityAuditEvent(
            user_id=user_id,
            actor_user_id=None,
            event_type=event_type,
            ip_address=_request_ip(request),
            event_metadata={"reason": reason},
        )
    )
    try:
        db.commit()
    except Exception:
        db.rollback()


def _oauth_failure(
    db: Session,
    request: Request,
    code: str,
    *,
    user_id: int | None = None,
    audit_reason: str | None = None,
) -> RedirectResponse:
    _record_failed_login(
        db,
        request,
        "oauth_login_failed",
        audit_reason or code,
        user_id=user_id,
    )
    response = RedirectResponse(
        url=f"/login?oauth_error={code}",
        status_code=status.HTTP_302_FOUND,
    )
    _clear_flow_cookie(response)
    return response


@router.get("/arena/start", response_class=RedirectResponse)
def start_arena_oauth(
    return_to: str = "/",
    db: Session = Depends(get_db),
    state_service: OAuthStateService = Depends(get_oauth_state_service),
    oauth_service: BfmeOAuthService = Depends(get_bfme_oauth_service),
):
    if not settings.BFME_OAUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "oauth_not_configured"},
        )

    issue = state_service.issue(db, return_to)
    response = RedirectResponse(
        url=oauth_service.build_authorize_url(issue.state),
        status_code=status.HTTP_302_FOUND,
    )
    _set_flow_cookie(response, issue.flow_token)
    return response


@router.get("/arena/callback", response_class=RedirectResponse)
async def finish_arena_oauth(
    request: Request,
    background_tasks: BackgroundTasks,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    state_service: OAuthStateService = Depends(get_oauth_state_service),
    oauth_service: BfmeOAuthService = Depends(get_bfme_oauth_service),
    onboarding_service: AccountOnboardingService = Depends(
        get_account_onboarding_service
    ),
    backfill_service: ArenaMatchBackfillService = Depends(
        get_arena_match_backfill_service
    ),
    session_service: SessionService = Depends(get_session_service),
):
    if error == "access_denied":
        return _oauth_failure(db, request, "access_denied")
    if error:
        safe_error = error if error in {
            "invalid_request",
            "unauthorized_client",
            "invalid_client",
            "invalid_grant",
            "unsupported_response_type",
            "server_error",
            "temporarily_unavailable",
        } else "other"
        return _oauth_failure(
            db,
            request,
            "arena_rejected",
            audit_reason=f"arena_rejected:callback:{safe_error}",
        )
    if not settings.BFME_OAUTH_ENABLED:
        return _oauth_failure(db, request, "oauth_not_configured")

    flow_token = request.cookies.get(settings.OAUTH_FLOW_COOKIE_NAME)
    if (
        not code
        or not code.strip()
        or not state
        or not state.strip()
        or not flow_token
    ):
        return _oauth_failure(db, request, "invalid_callback")

    try:
        login_state = state_service.consume(db, state, flow_token)
    except InvalidOAuthState:
        return _oauth_failure(db, request, "invalid_state")

    try:
        access_token = await oauth_service.exchange_code(code)
        try:
            identity = await oauth_service.fetch_identity(access_token)
        finally:
            del access_token
        user, _created = onboarding_service.get_or_create_arena_user(
            db,
            identity.uuid,
            identity.display_name,
        )
        if not user.is_active:
            return _oauth_failure(
                db,
                request,
                "inactive_account",
                user_id=user.id,
            )
        backfill_job, dispatch_backfill = backfill_service.ensure_queued(
            db,
            user,
        )
        issue = session_service.issue(
            db,
            user,
            ip_address=_request_ip(request),
            user_agent=_request_user_agent(request),
        )
    except ArenaOAuthUnavailable as exc:
        db.rollback()
        stage = exc.stage if exc.stage in {"token", "identity"} else "unknown"
        upstream_status = exc.status if isinstance(exc.status, int) else "unknown"
        safe_reason = exc.reason if exc.reason in {
            "transport",
            "invalid_json",
            "http",
            "payload_not_object",
            "payload_access_token",
            "payload_token_type",
            "payload_expires_in",
            "payload_scope",
            "payload_uuid",
            "payload_display_name",
        } else "unknown"
        return _oauth_failure(
            db,
            request,
            "arena_unavailable",
            audit_reason=(
                f"arena_unavailable:{stage}:{upstream_status}:{safe_reason}"
            ),
        )
    except ArenaOAuthRejected as exc:
        db.rollback()
        stage = exc.stage if exc.stage in {"token", "identity"} else "unknown"
        upstream_status = exc.status if exc.status in {400, 401, 403} else "unknown"
        provider_error = exc.provider_error or "unknown"
        code_shape = "code_whitespace" if any(character.isspace() for character in code) else "code_clean"
        return _oauth_failure(
            db,
            request,
            "arena_rejected",
            audit_reason=(
                f"arena_rejected:{stage}:{upstream_status}:"
                f"{provider_error}:{code_shape}"
            ),
        )
    except OnboardingValidationError:
        db.rollback()
        return _oauth_failure(db, request, "invalid_identity")
    except AccountIdentityConflict:
        db.rollback()
        return _oauth_failure(db, request, "account_conflict")
    except Exception:
        db.rollback()
        return _oauth_failure(db, request, "oauth_failed")

    return_to = (
        "/onboarding"
        if user.onboarding_completed_at is None
        else login_state.return_to
    )
    response = RedirectResponse(
        url=return_to,
        status_code=status.HTTP_302_FOUND,
    )
    set_session_cookie(response, issue.token)
    _clear_flow_cookie(response)
    if dispatch_backfill:
        background_tasks.add_task(
            backfill_service.process_job_by_id,
            backfill_job.id,
        )
    return response


@router.get("/session", response_model=SessionUserSummary)
def read_session(
    current_session: UserSession = Depends(_require_session),
):
    return _session_summary(current_session.user)


@router.post(
    "/password-recovery/request",
    response_model=PasswordRecoveryRequestResult,
)
def request_password_recovery(
    payload: PasswordRecoveryRequest,
    request: Request,
    db: Session = Depends(get_db),
    recovery_service: PasswordRecoveryService = Depends(
        get_password_recovery_service
    ),
):
    message = recovery_service.request(
        db,
        email=str(payload.email),
        client_ip=_request_ip(request) or "unknown",
    )
    return PasswordRecoveryRequestResult(message=message)


@router.post(
    "/password-recovery/confirm",
    response_model=PasswordRecoveryConfirmResult,
)
def confirm_password_recovery(
    payload: PasswordRecoveryConfirm,
    db: Session = Depends(get_db),
    recovery_service: PasswordRecoveryService = Depends(
        get_password_recovery_service
    ),
):
    recovery_service.confirm(
        db,
        token=payload.token,
        password=payload.password,
    )
    return PasswordRecoveryConfirmResult(
        message="Пароль изменён. Теперь можно войти в аккаунт.",
    )


@router.post("/onboarding", response_model=SessionUserSummary)
def complete_onboarding(
    payload: OnboardingRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(_require_session),
    onboarding_service: AccountOnboardingService = Depends(
        get_account_onboarding_service
    ),
    session_service: SessionService = Depends(get_session_service),
):
    user = current_session.user
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_session"},
        )
    user_id = user.id
    try:
        updated_user = onboarding_service.complete_onboarding(
            db,
            user,
            payload.history_mode,
            payload.language,
            payload.accepted_rules,
            password=payload.password,
            commit=False,
        )
        current_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
        revoked = session_service.revoke(
            db,
            current_token,
            commit=False,
        )
        if not revoked:
            raise RuntimeError("Текущая сессия не была отозвана")
        issue = session_service.issue(
            db,
            updated_user,
            ip_address=_request_ip(request),
            user_agent=_request_user_agent(request),
            commit=False,
        )
        db.commit()
    except OnboardingValidationError as exc:
        db.rollback()
        _record_failed_login(
            db,
            request,
            "onboarding_failed",
            "validation_failed",
            user_id=user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "onboarding_invalid"},
        ) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "session_transition_failed"},
        ) from exc
    set_session_cookie(response, issue.token)
    return _session_summary(updated_user)


def _current_identity_user(
    db: Session,
    nickname: str,
) -> User | None:
    nickname_key = canonical_nickname_key(nickname)
    candidates = (
        db.query(ExternalPlayerIdentity)
        .join(User, User.id == ExternalPlayerIdentity.user_id)
        .filter(
            ExternalPlayerIdentity.source == AccountOnboardingService.SOURCE,
            ExternalPlayerIdentity.current_nickname_key == nickname_key,
            ExternalPlayerIdentity.verification_status == "verified",
            ExternalPlayerIdentity.claimed_at.is_not(None),
            ExternalPlayerIdentity.verified_at.is_not(None),
            User.is_claimed.is_(True),
        )
        .limit(2)
        .all()
    )
    matching_candidates = [
        identity
        for identity in candidates
        if canonical_nickname_key(identity.current_nickname) == nickname_key
    ]
    if len(matching_candidates) != 1:
        return None
    return matching_candidates[0].user


def _reject_password_login(
    db: Session,
    request: Request,
    *,
    user_id: int | None = None,
) -> None:
    _record_failed_login(
        db,
        request,
        "password_login_failed",
        "invalid_credentials",
        user_id=user_id,
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "invalid_credentials"},
    )


@router.post("/password-login", response_model=SessionUserSummary)
def password_login(
    payload: PasswordLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
):
    user = _current_identity_user(db, payload.nickname)
    eligible_user = bool(
        user is not None and user.is_active and user.hashed_password
    )
    password_hash = (
        user.hashed_password if eligible_user else DUMMY_PASSWORD_HASH
    )
    valid_password = False
    try:
        valid_password = verify_password(payload.password, password_hash)
    except (TypeError, ValueError):
        valid_password = False
    if not eligible_user or not valid_password:
        _reject_password_login(
            db,
            request,
            user_id=user.id if user is not None else None,
        )

    issue = session_service.issue(
        db,
        user,
        ip_address=_request_ip(request),
        user_agent=_request_user_agent(request),
    )
    set_session_cookie(response, issue.token)
    return _session_summary(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    db: Session = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
):
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    try:
        session_service.revoke(db, token)
    except Exception:
        db.rollback()
        response = JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": {"code": "logout_failed"}},
        )
        clear_session_cookie(response)
        return response
    clear_session_cookie(response)
    return response


@router.post(
    "/impersonation/return",
    response_model=SessionUserSummary,
)
def return_from_impersonation(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
):
    """Возвращает подменённую сессию к реальному администратору."""
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    try:
        current_session = session_service.resolve(db, token)
    except InvalidSession:
        db.rollback()
        failure = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": {"code": "invalid_session"}},
        )
        clear_session_cookie(failure)
        return failure

    if not current_session.is_impersonation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "not_impersonating"},
        )

    actor = current_session.impersonated_by_user
    try:
        issue = session_service.rotate(
            db,
            token,
            actor,
            ip_address=_request_ip(request),
            user_agent=_request_user_agent(request),
            commit=False,
        )
        AdminAuditService().record(
            db,
            actor_user_id=actor.id,
            action="user_impersonation_returned",
            entity_type="user",
            entity_id=current_session.user_id,
            before_data={"effective_user_id": current_session.user_id},
        )
        db.commit()
    except InvalidSession:
        db.rollback()
        failure = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": {"code": "invalid_session"}},
        )
        clear_session_cookie(failure)
        return failure
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "session_transition_failed"},
        ) from exc

    actor.__dict__.pop("_is_admin_impersonation", None)
    actor.__dict__.pop("_impersonated_by_username", None)
    set_session_cookie(response, issue.token)
    return _session_summary(actor)


@router.post("/sessions/revoke-all", response_model=RevokeAllResponse)
def revoke_all_sessions(
    response: Response,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(_require_session),
    session_service: SessionService = Depends(get_session_service),
):
    user = current_session.user
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_session"},
        )
    revoked_count = session_service.revoke_all(db, user.id)
    clear_session_cookie(response)
    return RevokeAllResponse(revoked_count=revoked_count)
