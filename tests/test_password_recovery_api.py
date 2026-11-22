from fastapi.testclient import TestClient

from app.api.v1.oauth import get_password_recovery_service
from app.database import get_db
from app.main import app
from app.services.password_recovery_service import GENERIC_REQUEST_MESSAGE


class FakePasswordRecoveryService:
    def __init__(self):
        self.requests = []
        self.confirmations = []

    def request(self, db, *, email, client_ip):
        self.requests.append((db, email, client_ip))
        return GENERIC_REQUEST_MESSAGE

    def confirm(self, db, *, token, password):
        self.confirmations.append((db, token, password))


def test_password_recovery_http_contract(db):
    service = FakePasswordRecoveryService()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_password_recovery_service] = lambda: service
    try:
        with TestClient(app, base_url="https://testserver") as client:
            requested = client.post(
                "/api/v1/auth/password-recovery/request",
                json={"email": "hero@example.com"},
            )
            confirmed = client.post(
                "/api/v1/auth/password-recovery/confirm",
                json={"token": "a" * 32, "password": "new-password"},
            )
    finally:
        app.dependency_overrides.pop(get_password_recovery_service, None)
        app.dependency_overrides.pop(get_db, None)

    assert requested.status_code == 200
    assert requested.json() == {"accepted": True, "message": GENERIC_REQUEST_MESSAGE}
    assert service.requests[0][1:] == ("hero@example.com", "testclient")
    assert confirmed.status_code == 200
    assert confirmed.json() == {
        "changed": True,
        "message": "Пароль изменён. Теперь можно войти в аккаунт.",
    }
    assert service.confirmations[0][1:] == ("a" * 32, "new-password")
