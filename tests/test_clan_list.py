from fastapi.testclient import TestClient

from app.database import get_db
from app.core.auth import get_current_active_user
from app.main import app
from app.models.clan import Clan, ClanMember
from app.models.territory import Territory
from app.models.user import User


def test_my_clan_returns_null_when_user_has_no_clan(db):
    user = User(
        username="solo-player",
        email="solo-player@example.com",
        hashed_password="hash",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: user
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/clans/my")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_active_user, None)

    assert response.status_code == 200
    assert response.json() is None


def test_clan_list_includes_owned_territory_count(db):
    leader = User(
        username="leader",
        email="leader@example.com",
        hashed_password="hash",
    )
    db.add(leader)
    db.flush()

    clan = Clan(name="Test clan", leader_id=leader.id)
    db.add(clan)
    db.flush()
    db.add(ClanMember(user_id=leader.id, clan_id=clan.id, rank="Глава клана"))
    db.add(
        Territory(
            name="Test territory",
            region="Test region",
            svg_path_data="M 0 0 L 1 1",
            owner_clan_id=clan.id,
        )
    )
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/clans/")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()[0]["member_count"] == 1
    assert response.json()[0]["territory_count"] == 1


def test_clan_list_serializes_system_clan_without_leader(db):
    db.add(Clan(name="Системный полигон", leader_id=None, is_admin_clan=True))
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/clans/")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    system_clan = next(item for item in response.json() if item["name"] == "Системный полигон")
    assert system_clan["leader_id"] is None
    assert system_clan["is_admin_clan"] is True
