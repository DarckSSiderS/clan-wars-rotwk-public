from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.v1.presence import request_player_online
from app.models.notification import UserNotification
from app.models.role import Role
from app.models.user import User
from app.services.presence_service import OnlineRequestCooldown, PresenceService
from app.services.realtime_service import realtime_hub
from app.services.session_service import SessionService


def _players(db):
    role = Role(name="presence-user", description="Игрок")
    requester = User(
        username="PresenceRequester",
        email="presence-requester@example.test",
        hashed_password="unused",
        role=role,
        is_active=True,
        is_claimed=True,
    )
    target = User(
        username="PresenceTarget",
        email="presence-target@example.test",
        hashed_password="unused",
        role=role,
        is_active=True,
        is_claimed=True,
    )
    db.add_all([role, requester, target])
    db.commit()
    return requester, target


def test_presence_combines_websocket_heartbeat_and_last_session(db, monkeypatch):
    requester, target = _players(db)
    seen_at = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    SessionService().issue(db, target, now=seen_at)
    monkeypatch.setattr(
        realtime_hub,
        "online_user_ids",
        lambda user_ids: {requester.id}.intersection(user_ids),
    )

    statuses = PresenceService().get_many(db, {requester.id, target.id})

    by_user = {item["user_id"]: item for item in statuses}
    assert by_user[requester.id]["is_online"] is True
    assert by_user[requester.id]["last_seen_at"] is not None
    assert by_user[target.id] == {
        "user_id": target.id,
        "is_online": False,
        "last_seen_at": seen_at,
    }


def test_online_request_creates_notification_and_enforces_cooldown(db, monkeypatch):
    requester, target = _players(db)
    service = PresenceService()
    monkeypatch.setattr(realtime_hub, "online_user_ids", lambda _user_ids: set())
    monkeypatch.setattr(realtime_hub, "acquire_cooldown", lambda _key, _seconds: None)

    result = service.request_online(db, requester=requester, target=target)

    assert result["status"] == "requested"
    notification = db.query(UserNotification).filter_by(user_id=target.id).one()
    assert notification.notification_type == "online_request"
    assert requester.username in notification.message
    assert notification.link_url == f"/profile/{requester.username}"

    with pytest.raises(OnlineRequestCooldown):
        service.request_online(db, requester=requester, target=target)


def test_online_player_is_reported_without_redundant_notification(db, monkeypatch):
    requester, target = _players(db)
    monkeypatch.setattr(realtime_hub, "online_user_ids", lambda _user_ids: {target.id})

    result = PresenceService().request_online(
        db,
        requester=requester,
        target=target,
    )

    assert result["status"] == "already_online"
    assert result["is_online"] is True
    assert db.query(UserNotification).count() == 0


def test_online_request_rejects_self(db):
    requester, _ = _players(db)

    with pytest.raises(HTTPException) as exc_info:
        request_player_online(requester.id, requester, db)

    assert exc_info.value.status_code == 400
