from datetime import datetime, timezone
from hashlib import sha256

import pytest
from passlib.context import CryptContext
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.core.security import get_password_hash, verify_password
from app.core.time import as_utc
from app.models.auth_session import SecurityAuditEvent
from app.models.external_identity import (
    ExternalPlayerAlias,
    ExternalPlayerIdentity,
)
from app.models.role import Role
from app.models.user import User
from app.schemas.oauth import OnboardingRequest, SessionUserSummary
from app.schemas.user import User as UserSchema
from app.services.account_onboarding_service import (
    HISTORY_MODE_FULL,
    HISTORY_MODE_NEW,
    AccountIdentityConflict,
    AccountOnboardingService,
    OnboardingValidationError,
)


def create_role(db, name: str) -> Role:
    role = Role(name=name)
    db.add(role)
    db.commit()
    return role


def create_user(db, username: str, **values) -> User:
    user = User(username=username, **values)
    db.add(user)
    db.commit()
    return user


def attach_identity(
    db,
    user: User,
    external_uuid: str,
    nickname: str,
    *,
    verification_status: str = "unverified",
) -> ExternalPlayerIdentity:
    identity = ExternalPlayerIdentity(
        user_id=user.id,
        source="bfmeladder",
        external_uuid=external_uuid,
        current_nickname=nickname,
        verification_status=verification_status,
    )
    db.add(identity)
    db.flush()
    db.add(ExternalPlayerAlias(identity_id=identity.id, nickname=nickname))
    db.commit()
    return identity


def test_new_arena_account_is_claimed_active_and_uuid_bound(db, monkeypatch):
    monkeypatch.setattr(settings, "BFME_PRIMARY_ADMIN_UUID", "")

    user, created = AccountOnboardingService().get_or_create_arena_user(
        db,
        "  arena-uuid-1  ",
        "  Arena Player  ",
    )

    identity = db.query(ExternalPlayerIdentity).one()
    assert created is True
    assert user.username == "Arena Player"
    assert user.display_name == "Arena Player"
    assert user.email is None
    assert user.hashed_password is None
    assert user.is_claimed is True
    assert user.is_active is True
    assert user.onboarding_completed_at is None
    assert identity.user_id == user.id
    assert identity.source == "bfmeladder"
    assert identity.external_uuid == "arena-uuid-1"
    assert identity.current_nickname == "Arena Player"
    assert identity.verification_status == "verified"
    assert identity.claimed_at is not None
    assert identity.verified_at is not None
    assert {alias.nickname for alias in identity.aliases} == {"Arena Player"}


def test_repeated_uuid_keeps_user_role_and_records_nickname_aliases(
    db,
    monkeypatch,
):
    monkeypatch.setattr(settings, "BFME_PRIMARY_ADMIN_UUID", "different-uuid")
    role = create_role(db, "contentmaker")
    user = create_user(
        db,
        "internal-user",
        display_name="OldNick",
        role=role,
        is_claimed=False,
        is_active=False,
    )
    identity = attach_identity(db, user, "stable-uuid", "OldNick")

    same_user, created = AccountOnboardingService().get_or_create_arena_user(
        db,
        "stable-uuid",
        "NewNick",
    )

    db.refresh(identity)
    assert created is False
    assert same_user.id == user.id
    assert same_user.username == "internal-user"
    assert same_user.display_name == "NewNick"
    assert same_user.role_id == role.id
    assert same_user.is_claimed is True
    assert same_user.is_active is True
    assert identity.current_nickname == "NewNick"
    assert identity.verification_status == "verified"
    assert identity.claimed_at is not None
    assert identity.verified_at is not None
    assert {alias.nickname for alias in identity.aliases} == {
        "OldNick",
        "NewNick",
    }


def test_repeated_uuid_preserves_inactive_state_for_claimed_blocked_user(
    db,
    monkeypatch,
):
    monkeypatch.setattr(settings, "BFME_PRIMARY_ADMIN_UUID", "")
    user = create_user(
        db,
        "blocked-user",
        display_name="BlockedNick",
        is_claimed=True,
        is_active=False,
    )
    identity = attach_identity(db, user, "blocked-uuid", "BlockedNick")

    same_user, created = AccountOnboardingService().get_or_create_arena_user(
        db,
        "blocked-uuid",
        "RenamedBlockedNick",
    )

    db.refresh(identity)
    assert created is False
    assert same_user.id == user.id
    assert same_user.is_claimed is True
    assert same_user.is_active is False
    assert same_user.display_name == "RenamedBlockedNick"
    assert identity.current_nickname == "RenamedBlockedNick"
    assert identity.verification_status == "verified"


def test_nickname_collision_uses_deterministic_internal_username(
    db,
    monkeypatch,
):
    monkeypatch.setattr(settings, "BFME_PRIMARY_ADMIN_UUID", "")
    existing = create_user(
        db,
        "SameNick",
        display_name="SameNick",
        is_claimed=True,
    )
    digest = sha256(b"new-arena-uuid").hexdigest()

    user, created = AccountOnboardingService().get_or_create_arena_user(
        db,
        "new-arena-uuid",
        "SameNick",
    )

    assert created is True
    assert user.id != existing.id
    assert user.username == f"SameNick~{digest[:8]}"
    assert user.display_name == "SameNick"
    assert existing.display_name == "SameNick"


def test_username_suffix_grows_deterministically_when_first_suffix_is_taken(
    db,
    monkeypatch,
):
    monkeypatch.setattr(settings, "BFME_PRIMARY_ADMIN_UUID", "")
    digest = sha256(b"suffix-uuid").hexdigest()
    create_user(db, "TakenNick")
    create_user(db, f"TakenNick~{digest[:8]}")

    user, _ = AccountOnboardingService().get_or_create_arena_user(
        db,
        "suffix-uuid",
        "TakenNick",
    )

    assert user.username == f"TakenNick~{digest[:9]}"


def test_matching_nickname_never_claims_an_unrelated_user(db, monkeypatch):
    monkeypatch.setattr(settings, "BFME_PRIMARY_ADMIN_UUID", "")
    existing = create_user(
        db,
        "LegacyNick",
        display_name="LegacyNick",
        is_claimed=True,
    )

    arena_user, created = AccountOnboardingService().get_or_create_arena_user(
        db,
        "unrelated-uuid",
        "LegacyNick",
    )

    assert created is True
    assert arena_user.id != existing.id
    assert db.query(User).count() == 2
    assert db.query(ExternalPlayerIdentity).one().user_id == arena_user.id


@pytest.mark.parametrize(
    ("external_uuid", "display_name"),
    [
        ("", "Player"),
        ("   ", "Player"),
        ("u" * 81, "Player"),
        ("uuid", ""),
        ("uuid", "   "),
        ("uuid", "N" * 121),
    ],
)
def test_invalid_identity_fields_are_rejected_without_writes(
    db,
    external_uuid,
    display_name,
):
    with pytest.raises(OnboardingValidationError):
        AccountOnboardingService().get_or_create_arena_user(
            db,
            external_uuid,
            display_name,
        )

    assert db.query(User).count() == 0
    assert db.query(ExternalPlayerIdentity).count() == 0


def test_primary_admin_is_granted_only_by_configured_uuid(db, monkeypatch):
    admin_role = create_role(db, "admin")
    user_role = create_role(db, "user")
    monkeypatch.setattr(
        settings,
        "BFME_PRIMARY_ADMIN_UUID",
        "primary-admin-uuid",
    )

    primary, _ = AccountOnboardingService().get_or_create_arena_user(
        db,
        "primary-admin-uuid",
        "OrdinaryNick",
    )
    nickname_only, _ = AccountOnboardingService().get_or_create_arena_user(
        db,
        "ordinary-uuid",
        "darcks",
    )

    assert primary.role_id == admin_role.id
    assert nickname_only.role_id != admin_role.id
    assert nickname_only.role_id in {None, user_role.id}


def test_primary_admin_configuration_requires_existing_admin_role(
    db,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "BFME_PRIMARY_ADMIN_UUID",
        "primary-admin-uuid",
    )

    with pytest.raises(RuntimeError, match="admin"):
        AccountOnboardingService().get_or_create_arena_user(
            db,
            "primary-admin-uuid",
            "Player",
        )

    assert db.query(User).count() == 0
    assert len(db.new) == 0
    assert len(db.dirty) == 0


def test_missing_admin_role_does_not_mutate_existing_primary_identity(
    db,
    monkeypatch,
):
    user = create_user(
        db,
        "primary-imported",
        display_name="PrimaryOldNick",
        is_claimed=False,
        is_active=False,
    )
    attach_identity(db, user, "primary-existing-uuid", "PrimaryOldNick")
    monkeypatch.setattr(
        settings,
        "BFME_PRIMARY_ADMIN_UUID",
        "primary-existing-uuid",
    )

    with pytest.raises(RuntimeError, match="admin"):
        AccountOnboardingService().get_or_create_arena_user(
            db,
            "primary-existing-uuid",
            "PrimaryNewNick",
        )

    assert len(db.new) == 0
    assert len(db.dirty) == 0
    db.expire_all()
    persisted_identity = db.query(ExternalPlayerIdentity).one()
    assert persisted_identity.user.display_name == "PrimaryOldNick"
    assert persisted_identity.user.is_claimed is False
    assert persisted_identity.user.is_active is False
    assert persisted_identity.current_nickname == "PrimaryOldNick"
    assert persisted_identity.verification_status == "unverified"
    assert {alias.nickname for alias in persisted_identity.aliases} == {
        "PrimaryOldNick",
    }


def test_insert_integrity_error_without_uuid_becomes_identity_conflict(
    db,
    monkeypatch,
):
    monkeypatch.setattr(settings, "BFME_PRIMARY_ADMIN_UUID", "")

    def fail_commit():
        raise IntegrityError("INSERT", {}, Exception("duplicate"))

    monkeypatch.setattr(db, "commit", fail_commit)

    with pytest.raises(AccountIdentityConflict):
        AccountOnboardingService().get_or_create_arena_user(
            db,
            "conflicting-uuid",
            "ConflictNick",
        )

    assert len(db.new) == 0


def test_insert_integrity_error_claims_uuid_created_by_concurrent_writer(
    db,
    monkeypatch,
):
    monkeypatch.setattr(settings, "BFME_PRIMARY_ADMIN_UUID", "")
    concurrent_user = create_user(
        db,
        "imported-profile",
        display_name="ImportedNick",
        is_claimed=False,
        is_active=False,
    )
    concurrent_identity = attach_identity(
        db,
        concurrent_user,
        "concurrent-uuid",
        "ImportedNick",
    )
    service = AccountOnboardingService()
    lookup_count = 0

    def concurrent_lookup(db, external_uuid, source):
        nonlocal lookup_count
        lookup_count += 1
        return None if lookup_count == 1 else concurrent_identity

    original_commit = db.commit
    commit_count = 0

    def fail_first_commit():
        nonlocal commit_count
        commit_count += 1
        if commit_count == 1:
            raise IntegrityError("INSERT", {}, Exception("duplicate"))
        original_commit()

    monkeypatch.setattr(
        service.identity_service,
        "get_by_uuid",
        concurrent_lookup,
    )
    monkeypatch.setattr(db, "commit", fail_first_commit)

    user, created = service.get_or_create_arena_user(
        db,
        "concurrent-uuid",
        "OAuthNick",
    )

    db.refresh(concurrent_identity)
    assert created is False
    assert user.id == concurrent_user.id
    assert user.display_name == "OAuthNick"
    assert user.is_claimed is True
    assert user.is_active is True
    assert concurrent_identity.verification_status == "verified"
    assert {alias.nickname for alias in concurrent_identity.aliases} == {
        "ImportedNick",
        "OAuthNick",
    }


def test_existing_identity_claim_retries_full_update_after_integrity_error(
    db,
    monkeypatch,
):
    monkeypatch.setattr(settings, "BFME_PRIMARY_ADMIN_UUID", "")
    user = create_user(
        db,
        "race-profile",
        display_name="RaceOldNick",
        is_claimed=False,
        is_active=False,
    )
    attach_identity(db, user, "race-claim-uuid", "RaceOldNick")
    service = AccountOnboardingService()
    original_commit = db.commit
    commit_count = 0

    def fail_first_claim_commit():
        nonlocal commit_count
        commit_count += 1
        if commit_count == 1:
            raise IntegrityError("UPDATE", {}, Exception("alias race"))
        original_commit()

    monkeypatch.setattr(db, "commit", fail_first_claim_commit)

    claimed_user, created = service.get_or_create_arena_user(
        db,
        "race-claim-uuid",
        "RaceNewNick",
    )

    db.expire_all()
    persisted_identity = db.query(ExternalPlayerIdentity).one()
    aliases = {
        alias.nickname
        for alias in db.query(ExternalPlayerAlias).all()
    }
    assert commit_count == 2
    assert created is False
    assert claimed_user.id == user.id
    assert persisted_identity.user.is_claimed is True
    assert persisted_identity.user.is_active is True
    assert persisted_identity.verification_status == "verified"
    assert persisted_identity.claimed_at is not None
    assert persisted_identity.verified_at is not None
    assert persisted_identity.current_nickname == "RaceNewNick"
    assert aliases == {"RaceOldNick", "RaceNewNick"}


@pytest.mark.parametrize(
    ("history_mode", "language", "accepted_rules"),
    [
        (HISTORY_MODE_NEW, "ru", False),
        (HISTORY_MODE_NEW, "ru", 1),
        ("recent", "ru", True),
        (HISTORY_MODE_NEW, "fr", True),
    ],
)
def test_onboarding_rejects_invalid_rules_history_and_language(
    db,
    history_mode,
    language,
    accepted_rules,
):
    user = create_user(db, "onboarding-user")

    with pytest.raises(OnboardingValidationError):
        AccountOnboardingService().complete_onboarding(
            db,
            user,
            history_mode,
            language,
            accepted_rules,
        )

    db.refresh(user)
    assert user.onboarding_completed_at is None
    assert user.history_mode is None
    assert user.statistics_started_at is None
    assert db.query(SecurityAuditEvent).count() == 0


def test_new_history_sets_cutoff_and_blank_password_stays_disabled(db):
    user = create_user(db, "new-history-user")
    now = datetime(2026, 8, 22, 12, 30, tzinfo=timezone.utc)

    result = AccountOnboardingService().complete_onboarding(
        db,
        user,
        HISTORY_MODE_NEW,
        "de",
        True,
        password="   ",
        now=now,
    )

    event = db.query(SecurityAuditEvent).one()
    assert as_utc(result.onboarding_completed_at) == now
    assert as_utc(result.statistics_started_at) == now
    assert result.history_mode == HISTORY_MODE_NEW
    assert result.language == "de"
    assert result.hashed_password is None
    assert event.user_id == user.id
    assert event.event_type == "onboarding_completed"
    assert event.event_metadata == {
        "history_mode": HISTORY_MODE_NEW,
        "password_enabled": False,
    }


def test_full_history_leaves_cutoff_for_import_and_hashes_valid_password(db):
    user = create_user(db, "full-history-user")
    now = datetime(2026, 8, 22, 13, 0, tzinfo=timezone.utc)
    password = "very-strong-password"

    result = AccountOnboardingService().complete_onboarding(
        db,
        user,
        HISTORY_MODE_FULL,
        "en",
        True,
        password=password,
        now=now,
    )

    event = db.query(SecurityAuditEvent).one()
    assert as_utc(result.onboarding_completed_at) == now
    assert result.statistics_started_at is None
    assert result.history_mode == HISTORY_MODE_FULL
    assert result.language == "en"
    assert result.hashed_password != password
    assert verify_password(password, result.hashed_password) is True
    assert event.event_metadata == {
        "history_mode": HISTORY_MODE_FULL,
        "password_enabled": True,
    }
    assert password not in repr(event.event_metadata)
    assert result.hashed_password not in repr(event.event_metadata)


def test_new_password_hash_distinguishes_bytes_after_bcrypt_limit():
    first_password = "x" * 72 + "A"
    second_password = "x" * 72 + "B"

    hashed_password = get_password_hash(first_password)

    assert hashed_password.startswith("$bcrypt-sha256$")
    assert verify_password(first_password, hashed_password) is True
    assert verify_password(second_password, hashed_password) is False


def test_password_verification_accepts_legacy_bcrypt_hash():
    legacy_context = CryptContext(schemes=["bcrypt"])
    legacy_hash = legacy_context.hash("legacy-password")

    assert legacy_hash.startswith("$2")
    assert verify_password("legacy-password", legacy_hash) is True
    assert verify_password("different-password", legacy_hash) is False


@pytest.mark.parametrize("password", ["short", "x" * 129])
def test_nonblank_password_outside_allowed_length_is_rejected(db, password):
    user = create_user(db, "invalid-password-user")

    with pytest.raises(OnboardingValidationError):
        AccountOnboardingService().complete_onboarding(
            db,
            user,
            HISTORY_MODE_NEW,
            "ru",
            True,
            password=password,
        )

    db.refresh(user)
    assert user.hashed_password is None
    assert user.onboarding_completed_at is None


def test_repeated_onboarding_does_not_mutate_existing_history_choice(db):
    user = create_user(db, "completed-user")
    first_now = datetime(2026, 8, 22, 14, 0, tzinfo=timezone.utc)
    AccountOnboardingService().complete_onboarding(
        db,
        user,
        HISTORY_MODE_NEW,
        "ru",
        True,
        now=first_now,
    )

    with pytest.raises(OnboardingValidationError):
        AccountOnboardingService().complete_onboarding(
            db,
            user,
            HISTORY_MODE_FULL,
            "en",
            True,
            password="another-password",
            now=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
        )

    db.refresh(user)
    assert as_utc(user.onboarding_completed_at) == first_now
    assert as_utc(user.statistics_started_at) == first_now
    assert user.history_mode == HISTORY_MODE_NEW
    assert user.language == "ru"
    assert user.hashed_password is None
    assert db.query(SecurityAuditEvent).count() == 1


def test_onboarding_reloads_completion_state_before_mutating(db):
    user = create_user(db, "stale-onboarding-user")
    assert user.onboarding_completed_at is None
    other_db = sessionmaker(bind=db.get_bind())()
    first_now = datetime(2026, 8, 22, 15, 30, tzinfo=timezone.utc)
    try:
        other_user = other_db.get(User, user.id)
        AccountOnboardingService().complete_onboarding(
            other_db,
            other_user,
            HISTORY_MODE_FULL,
            "en",
            True,
            now=first_now,
        )
    finally:
        other_db.close()

    with pytest.raises(OnboardingValidationError):
        AccountOnboardingService().complete_onboarding(
            db,
            user,
            HISTORY_MODE_NEW,
            "ru",
            True,
            now=datetime(2026, 8, 22, 16, 0, tzinfo=timezone.utc),
        )

    db.refresh(user)
    assert as_utc(user.onboarding_completed_at) == first_now
    assert user.history_mode == HISTORY_MODE_FULL
    assert user.statistics_started_at is None
    assert db.query(SecurityAuditEvent).count() == 1


def test_onboarding_request_normalizes_blank_password_and_validates_literals():
    payload = OnboardingRequest(
        history_mode=HISTORY_MODE_NEW,
        language="ru",
        accepted_rules=True,
        password="   ",
    )

    assert payload.password is None

    with pytest.raises(ValidationError):
        OnboardingRequest(
            history_mode="recent",
            language="fr",
            accepted_rules=False,
            password="short",
        )


def test_onboarding_request_rejects_numeric_rules_acceptance():
    with pytest.raises(ValidationError):
        OnboardingRequest(
            history_mode=HISTORY_MODE_NEW,
            language="ru",
            accepted_rules=1,
        )


@pytest.mark.parametrize(
    "password",
    [
        "tiny",
        "long-secret-" + "x" * 129,
    ],
)
def test_onboarding_schema_redacts_rejected_password_from_error_json(password):
    with pytest.raises(ValidationError) as exc_info:
        OnboardingRequest(
            history_mode=HISTORY_MODE_NEW,
            language="ru",
            accepted_rules=True,
            password=password,
        )

    assert password not in exc_info.value.json()


def test_authenticated_user_schemas_support_oauth_user_without_email():
    now = datetime(2026, 8, 22, 16, 0, tzinfo=timezone.utc)
    user = User(
        id=42,
        username="ArenaUser",
        display_name="Arena User",
        email=None,
        is_active=True,
        is_claimed=True,
        balance=0,
        level=1,
        experience=0,
        language="ru",
        allow_clan_invites=True,
        created_at=now,
        onboarding_completed_at=now,
        history_mode=HISTORY_MODE_NEW,
        statistics_started_at=now,
    )

    session_payload = SessionUserSummary.model_validate(user)
    user_payload = UserSchema.model_validate(user)

    assert session_payload.email is None
    assert session_payload.display_name == "Arena User"
    assert session_payload.onboarding_completed_at == now
    assert session_payload.history_mode == HISTORY_MODE_NEW
    assert session_payload.statistics_started_at == now
    assert user_payload.email is None
    assert user_payload.onboarding_completed_at == now
    dumped = session_payload.model_dump()
    assert "hashed_password" not in dumped
    assert "external_uuid" not in dumped
