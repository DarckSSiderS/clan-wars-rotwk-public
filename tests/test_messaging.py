import pytest
from fastapi import HTTPException

from app.models.messaging import DirectMessage, DirectMessageReport, UserBlock
from app.models.notification import UserNotification
from app.models.user import User
from app.services.messaging_service import MessagingService


def _users(db):
    first = User(
        id=1,
        username="Yukio",
        email="yukio@example.test",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
    )
    second = User(
        id=2,
        username="Aragorn",
        email="aragorn@example.test",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
    )
    db.add_all([first, second])
    db.commit()
    return first, second


def test_direct_message_delivery_and_read_receipt(db):
    sender, recipient = _users(db)
    service = MessagingService()
    conversation = service.get_or_create(db, user=sender, username=recipient.username)

    message = service.send(
        db,
        user=sender,
        conversation_id=conversation["id"],
        body="  Собираемся у Белого города.  ",
    )
    assert message["body"] == "Собираемся у Белого города."
    assert db.query(UserNotification).filter(UserNotification.user_id == recipient.id).count() == 1
    notification = db.query(UserNotification).filter_by(user_id=recipient.id).one()
    assert notification.link_url == f"/messages?with={sender.username}"

    thread = service.list_messages(
        db,
        user=recipient,
        conversation_id=conversation["id"],
    )
    assert thread["total"] == 1
    assert thread["messages"][0]["sender_username"] == sender.username
    assert db.query(DirectMessage).one().read_at is not None


def test_messages_use_public_name_in_payloads_and_links(db):
    sender = User(
        username="Yukio~367fb5b7",
        display_name="Yukio",
        email="yukio-public@example.test",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
    )
    recipient = User(
        username="Aragorn",
        email="aragorn-public@example.test",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
    )
    db.add_all([sender, recipient])
    db.commit()
    service = MessagingService()

    conversation = service.get_or_create(db, user=recipient, username="Yukio")
    assert conversation["counterpart"]["username"] == sender.username
    assert conversation["counterpart"]["display_name"] == "Yukio"

    service.send(
        db,
        user=sender,
        conversation_id=conversation["id"],
        body="Скрытый внутренний идентификатор не должен попасть в интерфейс.",
    )
    notification = db.query(UserNotification).filter_by(user_id=recipient.id).one()
    assert notification.title == "Новое сообщение от Yukio"
    assert notification.link_url == "/messages?with=Yukio"


def test_unknown_message_recipient_does_not_create_a_profile(db):
    sender, _ = _users(db)
    initial_user_count = db.query(User).count()

    with pytest.raises(HTTPException) as error:
        MessagingService().get_or_create(db, user=sender, username="missing-player")

    assert error.value.status_code == 404
    assert db.query(User).count() == initial_user_count


def test_block_prevents_messages_and_report_is_audited(db):
    sender, recipient = _users(db)
    service = MessagingService()
    conversation = service.get_or_create(db, user=sender, username=recipient.username)
    sent = service.send(db, user=sender, conversation_id=conversation["id"], body="Test message")

    service.report(db, user=recipient, message_id=sent["id"], reason="Нежелательное сообщение")
    assert db.query(DirectMessageReport).count() == 1

    service.block(db, user=recipient, username=sender.username)
    assert db.query(UserBlock).count() == 1
    with pytest.raises(HTTPException) as error:
        service.send(db, user=sender, conversation_id=conversation["id"], body="Second message")
    assert error.value.status_code == 403

    service.unblock(db, user=recipient, username=sender.username)
    service.send(db, user=sender, conversation_id=conversation["id"], body="Allowed again")
    assert db.query(DirectMessage).count() == 2


def test_message_page_returns_newest_window_in_chronological_order(db):
    sender, recipient = _users(db)
    service = MessagingService()
    conversation = service.get_or_create(db, user=sender, username=recipient.username)

    for number in range(1, 6):
        service.send(
            db,
            user=sender,
            conversation_id=conversation["id"],
            body=f"Message {number}",
        )

    thread = service.list_messages(
        db,
        user=recipient,
        conversation_id=conversation["id"],
        limit=3,
    )

    assert thread["total"] == 5
    assert [message["body"] for message in thread["messages"]] == [
        "Message 3",
        "Message 4",
        "Message 5",
    ]
