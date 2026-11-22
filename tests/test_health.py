from datetime import timedelta

from fastapi.testclient import TestClient

from app.core.time import utc_now
from app.database import get_db
from app.main import app
from app.models.campaign import CampaignRuleSet
from app.models.worker import WorkerHeartbeat


def test_liveness_routes_do_not_require_database():
    with TestClient(app) as client:
        live = client.get("/health/live")
        legacy = client.get("/health")

    assert live.status_code == 200
    assert live.json() == {"status": "alive"}
    assert legacy.status_code == 200
    assert legacy.json() == {"status": "alive"}


def test_readiness_requires_rules_and_fresh_worker_without_leaking_details(db):
    db.add(
        CampaignRuleSet(
            version=1,
            values={},
            is_active=True,
            reason="test",
        )
    )
    db.add(
        WorkerHeartbeat(
            worker_name="campaign",
            heartbeat_at=utc_now(),
            last_success_at=utc_now(),
        )
    )
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            response = client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "components": {
            "database": "up",
            "campaign_rules": "up",
            "worker": "up",
        },
    }

    heartbeat = db.get(WorkerHeartbeat, "campaign")
    heartbeat.heartbeat_at = utc_now() - timedelta(hours=1)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            degraded = client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(get_db, None)

    payload = degraded.json()
    assert degraded.status_code == 503
    assert payload["status"] == "not_ready"
    assert payload["components"]["worker"] == "down"
    serialized = str(payload).lower()
    assert "postgresql" not in serialized
    assert "traceback" not in serialized
    assert "last_error" not in serialized
