from app.core.security import get_password_hash, verify_password
from app.models.password_recovery import PasswordRecoveryToken
from app.models.user import User
from app.services.password_recovery_service import (
    GENERIC_REQUEST_MESSAGE,
    PasswordRecoveryService,
)


class RecordingDelivery:
    def __init__(self):
        self.messages = []

    @staticmethod
    def is_configured():
        return True

    def send(self, *, recipient, token, language):
        self.messages.append({
            "recipient": recipient,
            "token": token,
            "language": language,
        })


def test_password_recovery_is_generic_and_changes_password_once(db):
    delivery = RecordingDelivery()
    service = PasswordRecoveryService(delivery=delivery)
    user = User(
        username="Recoverable",
        email="recoverable@example.test",
        hashed_password=get_password_hash("old-password"),
        is_active=True,
        is_claimed=True,
        auth_version=2,
        language="ru",
    )
    db.add(user)
    db.commit()

    message = service.request(
        db,
        email="RECOVERABLE@example.test",
        client_ip="127.0.0.1",
    )

    assert message == GENERIC_REQUEST_MESSAGE
    assert len(delivery.messages) == 1
    raw_token = delivery.messages[0]["token"]
    assert raw_token not in (db.query(PasswordRecoveryToken).one().token_hash or "")

    service.confirm(db, token=raw_token, password="new-password")
    db.refresh(user)

    assert verify_password("new-password", user.hashed_password)
    assert user.auth_version == 3
    assert db.query(PasswordRecoveryToken).one().used_at is not None


def test_unknown_recovery_email_has_same_response_without_delivery(db):
    delivery = RecordingDelivery()
    service = PasswordRecoveryService(delivery=delivery)

    message = service.request(
        db,
        email="missing@example.test",
        client_ip="127.0.0.2",
    )

    assert message == GENERIC_REQUEST_MESSAGE
    assert delivery.messages == []
    assert db.query(PasswordRecoveryToken).one().user_id is None
