from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.config import settings
from app.database import get_db
from app.main import app
from app.models.role import Role
from app.models.user import User
from app.services.campaign_history_service import CampaignHistoryService
from app.services.campaign_rule_service import CampaignRuleService
from app.services.session_service import SessionService


def _users(db):
    admin_role = Role(name="admin", description="Administrator")
    user_role = Role(name="campaign-api-user", description="User")
    admin = User(
        username="campaign-api-admin",
        email="campaign-api-admin@example.com",
        hashed_password="unused",
        role=admin_role,
        is_active=True,
        is_claimed=True,
    )
    user = User(
        username="campaign-api-user",
        email="campaign-api-user@example.com",
        hashed_password="unused",
        role=user_role,
        is_active=True,
        is_claimed=True,
    )
    db.add_all([admin_role, user_role, admin, user])
    db.commit()
    return admin, user


def _session_headers(db, user):
    token = SessionService().issue(db, user).token
    return {"Cookie": f"{settings.SESSION_COOKIE_NAME}={token}"}


@contextmanager
def _client(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_campaign_rule_routes_require_an_admin(db):
    _, user = _users(db)
    with _client(db) as client:
        assert client.get("/api/v1/admin/campaign-rules").status_code == 401
        assert client.get(
            "/api/v1/admin/campaign-rules",
            headers=_session_headers(db, user),
        ).status_code == 403


def test_public_handbook_rules_expose_current_and_historical_snapshots(db):
    admin, _ = _users(db)
    current = CampaignRuleService().get_active(db)
    season = CampaignHistoryService().create_season(
        db,
        starting_influence=100,
        reset_development=True,
        actor_user_id=None,
        name="Война за Север",
    )
    updated = CampaignRuleService().create_version(
        db,
        expected_version=current.version,
        changes={"WAR_DURATION_HOURS": 72},
        actor_user_id=admin.id,
        reason="Short active season",
    )
    db.commit()

    with _client(db) as client:
        active_response = client.get("/api/v1/campaign/rules/public")
        season_response = client.get(
            f"/api/v1/campaign/rules/public?season_id={season.id}"
        )
        missing_response = client.get("/api/v1/campaign/rules/public?season_id=999")

    assert active_response.status_code == 200
    assert active_response.json()["rule_set"] == {
        "id": updated.id,
        "version": updated.version,
        "values": dict(updated.values),
        "complete": True,
    }
    assert active_response.json()["season"]["name"] == "Война за Север"
    assert active_response.json()["season"]["rule_version"] == current.version
    assert season_response.status_code == 200
    assert season_response.json()["season"]["id"] == season.id
    assert season_response.json()["rule_set"]["version"] == current.version
    assert season_response.json()["rule_set"]["values"]["WAR_DURATION_HOURS"] == 60
    assert missing_response.status_code == 404


def test_admin_can_read_active_rules_and_schema(db):
    admin, _ = _users(db)
    with _client(db) as client:
        response = client.get(
            "/api/v1/admin/campaign-rules",
            headers=_session_headers(db, admin),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["active"]["version"] == 1
    assert payload["active"]["values"]["CLAN_ACTIVITY_WINDOW_DAYS"] == 28
    duration = next(
        item for item in payload["schema"] if item["key"] == "WAR_DURATION_HOURS"
    )
    assert duration["minimum"] == 1
    assert duration["unit"] == "hours"


def test_admin_can_update_list_and_restore_campaign_rules(db):
    admin, _ = _users(db)
    headers = _session_headers(db, admin)
    with _client(db) as client:
        updated = client.put(
            "/api/v1/admin/campaign-rules",
            headers=headers,
            json={
                "expected_version": 1,
                "reason": "Short campaign test",
                "changes": {"WAR_DURATION_HOURS": 72},
            },
        )
        history = client.get(
            "/api/v1/admin/campaign-rules/history?limit=10",
            headers=headers,
        )
        restored = client.post(
            "/api/v1/admin/campaign-rules/1/restore",
            headers=headers,
            json={
                "expected_version": 2,
                "reason": "Restore campaign defaults",
            },
        )

    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["values"]["WAR_DURATION_HOURS"] == 72
    assert [item["version"] for item in history.json()["items"]] == [2, 1]
    assert restored.status_code == 200
    assert restored.json()["version"] == 3
    assert restored.json()["values"]["WAR_DURATION_HOURS"] == 60


def test_stale_update_returns_structured_conflict(db):
    admin, _ = _users(db)
    headers = _session_headers(db, admin)
    with _client(db) as client:
        first = client.put(
            "/api/v1/admin/campaign-rules",
            headers=headers,
            json={
                "expected_version": 1,
                "reason": "First campaign update",
                "changes": {"WAR_DURATION_HOURS": 72},
            },
        )
        stale = client.put(
            "/api/v1/admin/campaign-rules",
            headers=headers,
            json={
                "expected_version": 1,
                "reason": "Stale campaign update",
                "changes": {"WAR_DURATION_HOURS": 48},
            },
        )

    assert first.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["detail"] == {
        "code": "campaign_rule_version_conflict",
        "expected_version": 1,
        "active_version": 2,
    }


def test_invalid_update_returns_structured_field_errors(db):
    admin, _ = _users(db)
    with _client(db) as client:
        response = client.put(
            "/api/v1/admin/campaign-rules",
            headers=_session_headers(db, admin),
            json={
                "expected_version": 1,
                "reason": "Invalid campaign update",
                "changes": {"WAR_ELO_MIN_POINTS": 100},
            },
        )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "campaign_rule_validation_failed"
    assert {
        "code": "range_order",
        "field": "WAR_ELO_MIN_POINTS",
    }.items() <= detail["errors"][0].items()
    assert detail["errors"][0]["message"]
