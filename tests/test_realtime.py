import asyncio
from contextlib import nullcontext
import json

from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

import app.api.v1.realtime as realtime_api
from app.config import settings
from app.main import app
from app.models.role import Role
from app.models.user import User
from app.services.messaging_service import MessagingService
from app.services.realtime_service import RealtimeHub, queue_realtime_event, realtime_hub
from app.services.session_service import SessionService


def _users_with_sessions(db):
    role = Role(name="user", description="Игрок")
    sender = User(
        username="RealtimeSender",
        email="realtime-sender@example.test",
        hashed_password="unused",
        role=role,
        is_active=True,
        is_claimed=True,
    )
    recipient = User(
        username="RealtimeRecipient",
        email="realtime-recipient@example.test",
        hashed_password="unused",
        role=role,
        is_active=True,
        is_claimed=True,
    )
    db.add_all([role, sender, recipient])
    db.commit()
    sender_token = SessionService().issue(db, sender).token
    recipient_token = SessionService().issue(db, recipient).token
    return sender, recipient, sender_token, recipient_token


def _cookie(token):
    return {"cookie": f"{settings.SESSION_COOKIE_NAME}={token}"}


class FakeWebSocket:
    def __init__(self):
        self.accepted = False
        self.messages = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, payload):
        self.messages.append(payload)


class FakeSyncRedis:
    def __init__(self):
        self.published = []

    def publish(self, channel, payload):
        self.published.append((channel, payload))


def test_redis_envelope_delivers_only_to_targeted_local_connections():
    async def scenario():
        hub = RealtimeHub(redis_url="", channel="test:realtime")
        target = FakeWebSocket()
        other = FakeWebSocket()
        await hub.connect(7, target)
        await hub.connect(8, other)

        await hub._deliver_serialized(hub._serialize({7}, {"type": "test.redis"}))
        await hub._deliver_serialized("not-json")

        assert target.accepted is True
        assert target.messages == [{"type": "test.redis"}]
        assert other.messages == []

    asyncio.run(scenario())


def test_impersonation_socket_receives_events_without_marking_player_online():
    async def scenario():
        hub = RealtimeHub(redis_url="", channel="test:realtime")
        socket = FakeWebSocket()

        await hub.connect(7, socket, mark_presence=False)

        assert hub.online_user_ids({7}) == set()
        await hub._broadcast({7}, {"type": "test.impersonation"})
        assert socket.messages == [{"type": "test.impersonation"}]

    asyncio.run(scenario())


def test_worker_process_publishes_serialized_event_to_redis():
    hub = RealtimeHub(redis_url="redis://127.0.0.1:6379/0", channel="test:realtime")
    fake_redis = FakeSyncRedis()
    hub._sync_redis = fake_redis

    hub.publish({12, 4}, {"type": "notification.created", "title": "Готово"})

    assert len(fake_redis.published) == 1
    channel, serialized = fake_redis.published[0]
    assert channel == "test:realtime"
    assert json.loads(serialized) == {
        "user_ids": [4, 12],
        "payload": {"type": "notification.created", "title": "Готово"},
    }


def test_realtime_events_publish_only_after_commit(db, monkeypatch):
    delivered = []
    monkeypatch.setattr(
        realtime_hub,
        "publish",
        lambda user_ids, payload: delivered.append((user_ids, payload)),
    )

    db.execute(text("SELECT 1"))
    queue_realtime_event(
        db,
        user_ids={7},
        payload={"type": "test.committed"},
    )
    assert delivered == []
    db.commit()
    assert delivered == [({7}, {"type": "test.committed"})]

    db.execute(text("SELECT 1"))
    queue_realtime_event(
        db,
        user_ids={8},
        payload={"type": "test.rolled_back"},
    )
    db.rollback()
    db.commit()
    assert len(delivered) == 1


def test_two_authenticated_sockets_receive_message_without_refresh(db, monkeypatch):
    sender, recipient, sender_token, recipient_token = _users_with_sessions(db)
    conversation = MessagingService().get_or_create(
        db,
        user=sender,
        username=recipient.username,
    )
    monkeypatch.setattr(realtime_api, "SessionLocal", lambda: nullcontext(db))

    with TestClient(app) as client:
        with client.websocket_connect(
            "/api/v1/realtime/ws",
            headers=_cookie(sender_token),
        ) as sender_socket:
            with client.websocket_connect(
                "/api/v1/realtime/ws",
                headers=_cookie(recipient_token),
            ) as recipient_socket:
                assert sender_socket.receive_json()["type"] == "realtime.ready"
                assert recipient_socket.receive_json()["type"] == "realtime.ready"

                sent = MessagingService().send(
                    db,
                    user=sender,
                    conversation_id=conversation["id"],
                    body="Сообщение в реальном времени",
                )

                sender_event = sender_socket.receive_json()
                recipient_notification = recipient_socket.receive_json()
                recipient_event = recipient_socket.receive_json()

                assert sender_event["type"] == "message.created"
                assert sender_event["message"]["id"] == sent["id"]
                assert recipient_notification["type"] == "notification.created"
                assert recipient_event["type"] == "message.created"
                assert recipient_event["message"]["body"] == "Сообщение в реальном времени"


def test_realtime_socket_rejects_missing_session(db, monkeypatch):
    monkeypatch.setattr(realtime_api, "SessionLocal", lambda: nullcontext(db))
    with TestClient(app) as client:
        try:
            with client.websocket_connect("/api/v1/realtime/ws") as socket:
                socket.receive_json()
            raise AssertionError("unauthenticated socket unexpectedly stayed connected")
        except WebSocketDisconnect as exc:
            assert exc.code == 4401
