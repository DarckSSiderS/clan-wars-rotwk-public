import asyncio
from datetime import datetime

import pytest

from app.api.v1.admin import (
    AdminArenaIdentityUpdate,
    get_admin_users,
    update_admin_arena_identity,
)
from app.api.v1.users import get_public_identity_directory
from app.api.v1.users import get_player_statistics
from app.models.external_identity import ExternalPlayerAlias, ExternalPlayerIdentity
from app.models.match import Match
from app.models.operation import AdminAuditLog
from app.models.role import Role
from app.models.user import User
from app.services.admin_identity_binding_service import AdminIdentityBindingService
from app.services.external_identity_service import ExternalIdentityService


def _users(db):
    admin_role = Role(name="admin", description="Администратор")
    user_role = Role(name="user", description="Игрок")
    admin = User(
        username="darcks",
        email="clanwar@example.test",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
        role=admin_role,
    )
    target = User(
        username="site-login",
        display_name="ArenaNick",
        email="player@example.test",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
        role=user_role,
    )
    db.add_all([admin_role, user_role, admin, target])
    db.commit()
    return admin, target


def test_admin_users_keep_login_and_public_arena_nickname_separate(db):
    admin, target = _users(db)

    payload = get_admin_users(admin, db)
    row = next(item for item in payload["users"] if item["id"] == target.id)

    assert row["username"] == "site-login"
    assert row["display_name"] == "ArenaNick"


def _arena_profile(db, role, *, username="ArenaNick", claimed=False):
    profile = User(
        username=username,
        email=f"{username.lower()}@profiles.invalid",
        hashed_password="unused" if claimed else "!",
        is_active=True,
        is_claimed=claimed,
        role=role,
    )
    db.add(profile)
    db.flush()
    identity = ExternalPlayerIdentity(
        user_id=profile.id,
        source="bfmeladder",
        external_uuid=f"uuid-{username.lower()}",
        current_nickname=username,
        verification_status="verified" if claimed else "unverified",
    )
    db.add(identity)
    db.flush()
    db.add(ExternalPlayerAlias(identity_id=identity.id, nickname=username))
    db.commit()
    return profile, identity


def test_admin_binding_moves_unclaimed_arena_profile_without_changing_login(db):
    admin, target = _users(db)
    source, identity = _arena_profile(db, target.role)

    result = AdminIdentityBindingService().bind(
        db,
        target_user=target,
        arena_nickname="ArenaNick",
        actor=admin,
        reason="Исправление привязки",
    )

    db.refresh(target)
    db.refresh(source)
    db.refresh(identity)
    assert result.id == identity.id
    assert target.username == "site-login"
    assert target.display_name == "ArenaNick"
    assert identity.user_id == target.id
    assert source.is_active is False
    assert source.username.startswith("arena-merged-")
    audit = db.query(AdminAuditLog).filter_by(action="arena_identity_rebound").one()
    assert audit.actor_user_id == admin.id
    assert audit.entity_id == str(target.id)
    assert audit.reason == "Исправление привязки"


def test_admin_binding_rejects_arena_profile_claimed_by_another_user(db):
    admin, target = _users(db)
    _arena_profile(db, target.role, username="TakenArenaNick", claimed=True)

    with pytest.raises(ValueError, match="уже привязан"):
        AdminIdentityBindingService().bind(
            db,
            target_user=target,
            arena_nickname="TakenArenaNick",
            actor=admin,
            reason="Проверка конфликта",
        )


def test_admin_endpoint_returns_separate_login_and_bound_arena_nickname(db):
    admin, target = _users(db)
    _arena_profile(db, target.role)

    payload = update_admin_arena_identity(
        target.id,
        AdminArenaIdentityUpdate(
            arena_nickname="ArenaNick",
            reason="Исправление ника пользователя",
        ),
        admin,
        db,
    )

    assert payload["username"] == "site-login"
    assert payload["display_name"] == "ArenaNick"
    assert payload["arena_nickname"] == "ArenaNick"
    assert payload["verification_status"] == "verified"

    directory = get_public_identity_directory(db)
    player = next(item for item in directory["players"] if item["username"] == "site-login")
    assert player["display_name"] == "ArenaNick"
    assert player["aliases"] == ["ArenaNick"]


def test_bound_account_resolves_login_and_all_arena_aliases(db):
    admin, target = _users(db)
    source, identity = _arena_profile(db, target.role)
    db.add(ExternalPlayerAlias(identity_id=identity.id, nickname="OldArenaNick"))
    db.commit()

    AdminIdentityBindingService().bind(
        db,
        target_user=target,
        arena_nickname="ArenaNick",
        actor=admin,
        reason="Исправление привязки",
    )

    names = ExternalIdentityService().names_for_user(db, target.id)
    assert names == {"site-login", "ArenaNick", "OldArenaNick"}


def test_profile_statistics_find_matches_by_bound_arena_nickname(db):
    admin, target = _users(db)
    _arena_profile(db, target.role)
    db.add(Match(
        match_id="arena-match-1",
        winner_player="ArenaNick",
        winner_faction="Men",
        loser_player="Opponent",
        loser_faction="Mordor",
        match_date=datetime(2026, 8, 12, 12, 0),
        game_mode="1 versus 1",
        map_name="Fords of Isen",
    ))
    db.commit()
    AdminIdentityBindingService().bind(
        db,
        target_user=target,
        arena_nickname="ArenaNick",
        actor=admin,
        reason="Исправление привязки",
    )

    statistics = asyncio.run(get_player_statistics("site-login", db))

    assert statistics["total_matches"] == 1
    assert statistics["wins"] == 1
