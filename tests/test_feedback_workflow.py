from contextlib import contextmanager
import io

from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.database import get_db
from app.main import app
from app.models.feedback import FeedbackMessage, FeedbackTicket
from app.models.notification import UserNotification
from app.models.operation import AdminAuditLog
from app.models.role import Role
from app.models.user import User
from app.services.session_service import SessionService


def _users(db):
    admin_role = Role(name="admin", description="Administrator")
    user_role = Role(name="feedback-user", description="User")
    admin = User(
        username="feedback-admin",
        email="feedback-admin@example.test",
        hashed_password="unused",
        role=admin_role,
        is_active=True,
        is_claimed=True,
    )
    reporter = User(
        username="reporter",
        email="reporter@example.test",
        hashed_password="unused",
        role=user_role,
        is_active=True,
        is_claimed=True,
    )
    stranger = User(
        username="stranger",
        email="stranger@example.test",
        hashed_password="unused",
        role=user_role,
        is_active=True,
        is_claimed=True,
    )
    db.add_all([admin_role, user_role, admin, reporter, stranger])
    db.commit()
    return admin, reporter, stranger


def _headers(db, user):
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


def _png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (320, 180), (25, 34, 29)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_feedback_ticket_reaches_admin_and_supports_two_way_workflow(db, tmp_path, monkeypatch):
    admin, reporter, stranger = _users(db)
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    with _client(db) as client:
        created = client.post(
            "/api/v1/feedback/tickets",
            headers=_headers(db, reporter),
            data={
                "category": "bug",
                "title": "Реликвия перекрывает карточку",
                "description": "Крупное изображение выходит за область карточки клана.",
                "reproduction_steps": "Открыть клан и перейти на вкладку реликвий.",
                "expected_result": "Изображение находится внутри превью.",
                "actual_result": "Изображение перекрывает описание и кнопку.",
                "source_path": "/clans/2?secret=must-not-be-stored",
                "user_agent": "Test Browser 1.0",
            },
            files={"image": ("relic.png", _png_bytes(), "image/png")},
        )

        assert created.status_code == 201
        ticket = created.json()
        assert ticket["reference"] == "CW-000001"
        assert ticket["source_path"] == "/clans/2"
        assert ticket["attachment_url"].startswith("/images/feedback/")
        assert (tmp_path / ticket["attachment_url"].removeprefix("/images/")).exists()
        assert db.query(UserNotification).filter_by(user_id=admin.id).count() == 1

        assert client.get(
            f"/api/v1/feedback/tickets/{ticket['id']}",
            headers=_headers(db, stranger),
        ).status_code == 404

        queue = client.get(
            "/api/v1/admin/feedback/tickets",
            headers=_headers(db, admin),
        )
        assert queue.status_code == 200
        assert queue.json()["summary"] == {
            "total": 1,
            "unread": 1,
            "new": 1,
            "in_progress": 0,
            "critical": 0,
        }

        updated = client.patch(
            f"/api/v1/admin/feedback/tickets/{ticket['id']}",
            headers=_headers(db, admin),
            json={"status": "in_progress", "priority": "critical", "assign_to_me": True},
        )
        assert updated.status_code == 200
        assert updated.json()["assigned_admin_name"] == admin.username
        assert updated.json()["priority"] == "critical"

        answered = client.post(
            f"/api/v1/admin/feedback/tickets/{ticket['id']}/replies",
            headers=_headers(db, admin),
            json={"body": "Спасибо, нашли причину. Исправление готовится."},
        )
        assert answered.status_code == 200
        assert answered.json()["status"] == "waiting_user"
        assert answered.json()["messages"][0]["is_admin"] is True

        reporter_reply = client.post(
            f"/api/v1/feedback/tickets/{ticket['id']}/replies",
            headers=_headers(db, reporter),
            json={"body": "Проверю после обновления."},
        )
        assert reporter_reply.status_code == 200
        assert reporter_reply.json()["status"] == "in_progress"
        assert reporter_reply.json()["admin_unread"] is True

    assert db.query(FeedbackTicket).count() == 1
    assert db.query(FeedbackMessage).count() == 2
    assert db.query(AdminAuditLog).filter(
        AdminAuditLog.entity_type == "feedback_ticket"
    ).count() == 2
    assert db.query(UserNotification).filter_by(user_id=reporter.id).count() >= 2


def test_feedback_and_balance_admin_routes_are_protected(db, monkeypatch):
    admin, reporter, _ = _users(db)
    monkeypatch.setattr(
        "app.api.v1.admin_balance.BalanceSimulationCatalogLoader.load",
        lambda _self, _db, rule_version=None: "catalog",
    )
    monkeypatch.setattr(
        "app.api.v1.admin_balance.BalanceSimulationService.run",
        lambda _self, catalog, days=30: {
            "rule_set": {"id": 1, "version": 2},
            "horizon_days": days,
            "scenarios": [],
            "signals": [],
            "recommendations": [],
        },
    )
    monkeypatch.setattr(
        "app.api.v1.admin_balance.StrategicSimulationService.run",
        lambda _self, catalog, payload: {
            "rule_set": {"id": 1, "version": 2},
            "economy": {},
            "war": {},
            "trade": {},
        },
    )
    sandbox_payload = {
        "economy": {
            "starting_territory_ids": [1],
            "starting_resources": {
                "gold": 500,
                "iron": 10,
                "wood": 10,
                "food": 5,
                "mithril": 2,
                "influence": 100,
            },
        },
        "war": {"source_territory_id": 1, "target_territory_id": 2},
        "trade": {
            "source_territory_id": 1,
            "target_territory_id": 2,
            "give_resource": "wood",
            "receive_resource": "iron",
        },
    }

    with _client(db) as client:
        assert client.get("/api/v1/admin/feedback/tickets").status_code == 401
        assert client.get(
            "/api/v1/admin/balance-simulator",
            headers=_headers(db, reporter),
        ).status_code == 403
        response = client.get(
            "/api/v1/admin/balance-simulator?days=14",
            headers=_headers(db, admin),
        )
        assert client.post(
            "/api/v1/admin/balance-simulator/sandbox",
            headers=_headers(db, reporter),
            json=sandbox_payload,
        ).status_code == 403
        sandbox_response = client.post(
            "/api/v1/admin/balance-simulator/sandbox",
            headers=_headers(db, admin),
            json=sandbox_payload,
        )

    assert response.status_code == 200
    assert response.json()["horizon_days"] == 14
    assert sandbox_response.status_code == 200
    assert sandbox_response.json()["rule_set"]["version"] == 2
