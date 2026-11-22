import pytest
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute, iter_route_contexts

from app.config import settings
from app.core.auth import (
    get_current_active_user,
    get_current_admin_user,
    get_onboarded_active_user,
)
from app.database import get_db
from app.main import app
from app.models.role import Role
from app.models.user import User
from app.services.session_service import SessionService


ADMIN_ONLY_MUTATIONS = {
    "POST /api/v1/campaign/seasons/start",
    "PATCH /api/v1/admin/clans/{clan_id:int}/cycle-economy",
    "POST /api/v1/campaign/cycles/admin/cycles/{cycle_id}/recover-preparation",
    "POST /api/v1/campaign/cycles/battles/{battle_id}/late-replays/{match_id}",
    "POST /api/v1/campaign/cycles/{cycle_id}/interception/review/contributions",
    "POST /api/v1/campaign/cycles/{cycle_id}/interception/review/adjustments",
    "POST /api/v1/campaign/cycles/{cycle_id}/interception/review/outcome/preview",
    "POST /api/v1/campaign/cycles/{cycle_id}/interception/review/outcome/confirm",
    "POST /api/v1/campaign/cycles/battles/{battle_id}/ownership",
    "POST /api/v1/campaign/cycles/seasons/{season_id}/start",
    "POST /api/v1/campaign/cycles/{cycle_id}/request-season-end",
    "POST /api/v1/campaign/cycles/battles/{battle_id}/adjustments",
    "POST /api/v1/campaign/cycles/battles/{battle_id}/review",
    "DELETE /api/v1/admin/clans/{clan_id}",
    "DELETE /api/v1/admin/wars/{war_id}",
    "POST /api/v1/admin/wars/{war_id}/points",
    "POST /api/v1/achievements/",
    "PUT /api/v1/achievements/{achievement_id:int}",
    "DELETE /api/v1/achievements/{achievement_id:int}",
    "POST /api/v1/achievements/my-achievements/{achievement_id:int}/create",
    "PUT /api/v1/achievements/my-achievements/{achievement_id:int}/progress",
    "PUT /api/v1/achievements/my-achievements/{achievement_id:int}/complete",
    "POST /api/v1/admin/titles",
    "PATCH /api/v1/admin/titles/{title_id:int}",
    "POST /api/v1/admin/titles/{title_id:int}/users/{user_id:int}",
    "DELETE /api/v1/admin/titles/{title_id:int}/users/{user_id:int}",
    "PATCH /api/v1/admin/users/{user_id:int}/role",
    "PATCH /api/v1/admin/users/{user_id:int}/arena-identity",
    "PATCH /api/v1/admin/clans/{clan_id}/economy",
    "PATCH /api/v1/admin/territories/{territory_id}",
    "POST /api/v1/admin/wars/{war_id}/recalculate",
    "PATCH /api/v1/admin/wars/{war_id}/matches/{result_id}",
    "POST /api/v1/admin/wars/{war_id}/extend",
    "POST /api/v1/admin/wars/{war_id}/finish",
    "POST /api/v1/admin/wars/{war_id}/cancel",
    "PUT /api/v1/admin/campaign-rules",
    "POST /api/v1/admin/campaign-rules/{version:int}/restore",
    "POST /api/v1/campaign/seasons/current/complete",
    "POST /api/v1/clans/assets/admin",
    "PUT /api/v1/clans/assets/admin/{asset_id:int}",
    "DELETE /api/v1/clans/assets/admin/{asset_id:int}",
    "POST /api/v1/clans/{clan_id:int}/admin-members/{user_id:int}",
    "DELETE /api/v1/clans/{clan_id:int}/admin-members/{user_id:int}",
    "POST /api/v1/clans/{clan_id:int}/admin-sandbox/reset",
    "POST /api/v1/localization/",
    "PUT /api/v1/localization/{identifier}",
    "DELETE /api/v1/localization/{identifier}",
    "POST /api/v1/scheduler/replays/{replay_id}/download",
    "PUT /api/v1/scheduler/campaign-settings",
    "POST /api/v1/scheduler/campaign/pause",
    "POST /api/v1/scheduler/campaign/resume",
    "POST /api/v1/scheduler/fetch-matches",
    "POST /api/v1/shop/items/",
    "PUT /api/v1/shop/items/{item_id:int}",
    "DELETE /api/v1/shop/items/{item_id:int}",
    "POST /api/v1/territories/season/start",
    "POST /api/v1/territories/",
    "PUT /api/v1/territories/{territory_id:int}",
    "DELETE /api/v1/territories/{territory_id:int}",
    (
        "POST /api/v1/territories/{territory_id:int}"
        "/attacking-clans/{clan_id:int}"
    ),
    (
        "POST /api/v1/territories/{territory_id:int}"
        "/defending-clans/{clan_id:int}"
    ),
    "DELETE /api/v1/territories/{territory_id:int}/clans/{clan_id:int}",
    "POST /api/v1/users/{user_id:int}/impersonate",
    "PUT /api/v1/users/{user_id:int}/external-identity/verification",
    "PUT /api/v1/users/{user_id:int}/balance",
    "POST /api/v1/wars/territories/",
    "PUT /api/v1/wars/territories/{territory_id:int}",
    "DELETE /api/v1/wars/territories/{territory_id:int}",
    "PUT /api/v1/wars/{war_id:int}/status",
    "PUT /api/v1/wars/{war_id:int}/end",
    "POST /api/v1/wars/participants/",
    "DELETE /api/v1/wars/{war_id:int}/participants/{user_id:int}",
    "PUT /api/v1/wars/{war_id:int}/participants/{user_id:int}/stats",
    "POST /api/v1/admin/feedback/tickets/{ticket_id:int}/read",
    "PATCH /api/v1/admin/feedback/tickets/{ticket_id:int}",
    "POST /api/v1/admin/feedback/tickets/{ticket_id:int}/replies",
    "POST /api/v1/admin/balance-simulator/sandbox",
}

ACCOUNT_SAFE_MUTATIONS = {
    "POST /api/v1/discord/link",
    "DELETE /api/v1/discord/link",
    "POST /api/v1/auth/onboarding",
    "POST /api/v1/auth/password-login",
    "POST /api/v1/auth/password-recovery/request",
    "POST /api/v1/auth/password-recovery/confirm",
    "POST /api/v1/auth/logout",
    "POST /api/v1/auth/impersonation/return",
    "POST /api/v1/auth/sessions/revoke-all",
    "POST /api/v1/users/me/external-identity/verification-request",
    "POST /api/v1/users/avatar",
    "POST /api/v1/users/{user_id:int}/avatar",
    "PUT /api/v1/users/{user_id:int}",
    "PUT /api/v1/notifications/read-all",
    "PUT /api/v1/notifications/{notification_id:int}/read",
    "POST /api/v1/feedback/tickets",
    "POST /api/v1/feedback/tickets/{ticket_id:int}/replies",
    "POST /api/v1/presence/{target_user_id:int}/online-request",
}

GAMEPLAY_MUTATIONS = {
    "POST /api/v1/campaign/preseason/clans/{clan_id}/lands/preview",
    "POST /api/v1/campaign/preseason/clans/{clan_id}/lands",
    "POST /api/v1/campaign/preseason/clans/{clan_id}/relics",
    "PUT /api/v1/campaign/cycles/{cycle_id}/clans/{clan_id}/defence-template",
    "PUT /api/v1/campaign/cycles/{cycle_id}/clans/{clan_id}/plan",
    "POST /api/v1/campaign/cycles/diplomacy/cycles/{cycle_id}/clans/{clan_id}",
    "POST /api/v1/campaign/cycles/economy/seasons/{season_id}/clans/{clan_id}/initialize",
    "POST /api/v1/campaign/cycles/economy/seasons/{season_id}/clans/{clan_id}/starters",
    "POST /api/v1/campaign/cycles/economy/seasons/{season_id}/clans/{clan_id}/relics",
    "PUT /api/v1/campaign/cycles/economy/seasons/{season_id}/clans/{clan_id}/active-relics",
    "POST /api/v1/campaign/cycles/economy/seasons/{season_id}/clans/{clan_id}/upgrades",
    "POST /api/v1/campaign/cycles/economy/seasons/{season_id}/clans/{clan_id}/market",
    "POST /api/v1/campaign/cycles/market/cycles/{cycle_id}/clans/{clan_id}/offers",
    "POST /api/v1/campaign/cycles/market/cycles/{cycle_id}/clans/{clan_id}/offers/{offer_id}/accept",
    "POST /api/v1/campaign/cycles/market/cycles/{cycle_id}/clans/{clan_id}/offers/{offer_id}/cancel",
    "POST /api/v1/campaign/cycles/{cycle_id}/clans/{clan_id}/scout",
    "POST /api/v1/campaign/cycles/{cycle_id}/clans/{clan_id}/reinforcements/requests",
    "POST /api/v1/campaign/cycles/{cycle_id}/clans/{clan_id}/reinforcements/dispatches",
    "POST /api/v1/campaign/cycles/{cycle_id}/clans/{clan_id}/startup/preview",
    "POST /api/v1/campaign/cycles/{cycle_id}/clans/{clan_id}/startup/claim",
    "POST /api/v1/clans/",
    "POST /api/v1/clans/with-assets",
    "PUT /api/v1/clans/{clan_id:int}",
    "DELETE /api/v1/clans/{clan_id:int}",
    "POST /api/v1/clans/{clan_id:int}/assets/purchase",
    "PUT /api/v1/clans/{clan_id:int}/assets/loadout",
    "PUT /api/v1/clans/{clan_id:int}/members/{user_id:int}/trader",
    "PUT /api/v1/clans/{clan_id:int}/members/{user_id:int}/role",
    "PUT /api/v1/clans/{clan_id:int}/members/{user_id:int}/warlord",
    "POST /api/v1/clans/market/offers",
    "POST /api/v1/clans/market/offers/{offer_id:int}/accept",
    "POST /api/v1/clans/market/offers/{offer_id:int}/cancel",
    "POST /api/v1/clans/{clan_id:int}/invite",
    "PUT /api/v1/clans/invites/{invite_id:int}",
    "POST /api/v1/clans/{clan_id:int}/applications",
    "POST /api/v1/clans/{clan_id:int}/leave",
    "DELETE /api/v1/clans/{clan_id:int}/members/{user_id:int}",
    "POST /api/v1/clans/{clan_id:int}/avatar",
    "POST /api/v1/clans/{clan_id:int}/transfer-leadership",
    "PUT /api/v1/clans/applications/{application_id:int}",
    "POST /api/v1/quests/claim/{quest_id}",
    "POST /api/v1/quests/refresh-daily",
    "POST /api/v1/quests/refresh-weekly",
    "POST /api/v1/quests/update-progress",
    "POST /api/v1/shop/purchase/",
    "POST /api/v1/shop/equip/",
    "POST /api/v1/shop/unequip/{user_item_id:int}",
    "POST /api/v1/territories/{territory_id:int}/upgrade",
    "POST /api/v1/wars/",
    "POST /api/v1/clans/{clan_id:int}/diplomacy/{other_clan_id:int}",
    "POST /api/v1/messages/conversations/{username}",
    "POST /api/v1/messages/conversations/{conversation_id:int}/messages",
    "PUT /api/v1/messages/blocks/{username}",
    "DELETE /api/v1/messages/blocks/{username}",
    "POST /api/v1/messages/{message_id:int}/report",
}

MUTATION_MATRIX = {
    **{route: "admin-only" for route in ADMIN_ONLY_MUTATIONS},
    **{route: "account-safe" for route in ACCOUNT_SAFE_MUTATIONS},
    **{route: "gameplay" for route in GAMEPLAY_MUTATIONS},
}


def _registered_mutations():
    methods = {"POST", "PUT", "PATCH", "DELETE"}
    return {
        f"{method} {route.path}": route
        for route in iter_route_contexts(app.routes)
        if isinstance(route.original_route, APIRoute) and route.path.startswith("/api/v1")
        for method in route.methods & methods
    }


def _direct_dependencies(route):
    return {dependency.call for dependency in route.dependant.dependencies}


def test_every_mutating_route_has_an_explicit_permission_classification():
    registered = _registered_mutations()

    assert not (ADMIN_ONLY_MUTATIONS & ACCOUNT_SAFE_MUTATIONS
                or ADMIN_ONLY_MUTATIONS & GAMEPLAY_MUTATIONS
                or ACCOUNT_SAFE_MUTATIONS & GAMEPLAY_MUTATIONS)
    assert set(registered) == set(MUTATION_MATRIX)


def test_mutating_routes_use_the_dependency_required_by_their_class():
    registered = _registered_mutations()

    for route_key, classification in MUTATION_MATRIX.items():
        dependencies = _direct_dependencies(registered[route_key])
        if classification == "gameplay":
            assert get_onboarded_active_user in dependencies, route_key
            assert get_current_active_user not in dependencies, route_key
        elif classification == "admin-only":
            assert get_current_admin_user in dependencies, route_key
            assert get_onboarded_active_user not in dependencies, route_key
        else:
            assert get_onboarded_active_user not in dependencies, route_key


@pytest.fixture()
def incomplete_user_client(db):
    role = Role(name="user", description="Обычный пользователь")
    user = User(
        username="onboarding-boundary-user",
        email="onboarding-boundary@example.test",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
        onboarding_completed_at=None,
    )
    user.role = role
    db.add(user)
    db.commit()
    issue = SessionService().issue(db, user)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app, base_url="https://testserver") as client:
            client.cookies.set(
                settings.SESSION_COOKIE_NAME,
                issue.token,
                domain="testserver.local",
                path="/",
            )
            yield client, user
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/clans/"),
        ("POST", "/api/v1/clans/market/offers"),
        ("POST", "/api/v1/clans/1/assets/purchase"),
        ("POST", "/api/v1/wars/"),
        ("POST", "/api/v1/territories/1/upgrade"),
        ("POST", "/api/v1/shop/purchase/"),
        ("POST", "/api/v1/quests/claim/1"),
        ("PUT", "/api/v1/campaign/cycles/1/clans/1/plan"),
        ("POST", "/api/v1/campaign/cycles/economy/seasons/1/clans/1/market"),
        ("POST", "/api/v1/campaign/cycles/diplomacy/cycles/1/clans/1"),
        ("POST", "/api/v1/campaign/cycles/market/cycles/1/clans/1/offers"),
        ("POST", "/api/v1/campaign/cycles/1/clans/1/scout"),
        ("POST", "/api/v1/campaign/cycles/1/clans/1/reinforcements/requests"),
        ("POST", "/api/v1/campaign/cycles/1/clans/1/startup/claim"),
    ],
)
def test_incomplete_user_is_rejected_at_each_gameplay_domain_boundary(
    incomplete_user_client,
    method,
    path,
):
    client, _user = incomplete_user_client

    response = client.request(method, path)

    assert response.status_code == 403
    assert response.json() == {"detail": "onboarding_required"}


def test_incomplete_user_can_read_public_data_and_session(
    incomplete_user_client,
):
    client, _user = incomplete_user_client

    public_response = client.get("/api/v1/clans/")
    session_response = client.get("/api/v1/auth/session")

    assert public_response.status_code == 200
    assert session_response.status_code == 200
    assert session_response.json()["onboarding_required"] is True


def test_incomplete_user_can_update_account_safe_profile_settings(
    incomplete_user_client,
):
    client, user = incomplete_user_client

    response = client.put(
        f"/api/v1/users/{user.id}",
        json={"language": "de", "allow_clan_invites": False},
    )

    assert response.status_code == 200
    assert response.json()["language"] == "de"
    assert response.json()["allow_clan_invites"] is False


def test_incomplete_user_can_complete_onboarding(incomplete_user_client):
    client, _user = incomplete_user_client

    response = client.post(
        "/api/v1/auth/onboarding",
        json={
            "history_mode": "new",
            "language": "ru",
            "accepted_rules": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["onboarding_required"] is False
