import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

from app.models.clan import Clan, ClanMember
from app.models.war import ClanWar
from app.models.user import User
from app.services.admin_deletion_service import AdminDeletionService
from app.services.war_service import ClanWarService
from app.schemas.war import ClanWarDetails
from tests.test_war_creation_v3 import _rules, _clan, _territory, _payload


@pytest.fixture(autouse=True)
def enforce_foreign_keys(db):
    db.execute(text("PRAGMA foreign_keys=ON"))
    from app.models.role import Role
    db.add_all([Role(id=1, name="admin"), Role(id=2, name="user")])
    db.commit()
    yield
    db.rollback()
    db.execute(text("PRAGMA foreign_keys=OFF"))


def test_delete_api_requires_admin_and_matching_confirmation(db):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import get_db
    from app.core.auth import get_current_admin_user
    clan = Clan(name="Protected by confirmation")
    db.add(clan)
    db.commit()
    with TestClient(app) as client:
        response = client.request("DELETE", f"/api/v1/admin/clans/{clan.id}", json={"confirmation_id": clan.id, "reason": "test"})
        assert response.status_code in (401, 403)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_admin_user] = lambda: User(id=999)
    try:
        with TestClient(app) as client:
            response = client.request("DELETE", f"/api/v1/admin/clans/{clan.id}", json={"confirmation_id": clan.id + 1, "reason": "test"})
            assert response.status_code == 422
            assert db.get(Clan, clan.id) is not None
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_admin_user, None)


def test_permanent_clan_deletion_keeps_opponent_war_and_users(db):
    _rules(db)
    clan, leader, fighters = _clan(db, "purge")
    opponent, _, _ = _clan(db, "survivor")
    target = _territory(db, "purge")
    db.commit()
    service = ClanWarService()
    war = service.create_war(db, _payload(target, fighters), leader)
    war.defending_clan_id = opponent.id
    war.war_type = "territory_attack"
    target.owner_clan_id = clan.id
    db.commit()
    clan_id, leader_id, war_id = clan.id, leader.id, war.id
    AdminDeletionService().delete_clan(db, clan_id)
    db.commit()
    assert db.scalar(select(Clan).where(Clan.id == clan_id)) is None
    assert db.scalar(select(ClanMember).where(ClanMember.clan_id == clan_id)) is None
    assert db.get(User, leader_id) is not None
    preserved = db.get(ClanWar, war_id)
    assert preserved.status == "canceled"
    assert preserved.attacking_clan_id is None
    assert preserved.defending_clan_id == opponent.id
    assert target.owner_clan_id is None
    ClanWarDetails.model_validate(service.serialize_war(db, preserved))


def test_permanent_war_deletion_releases_attack_and_keeps_players(db):
    _rules(db)
    clan, leader, fighters = _clan(db, "purge-war")
    target = _territory(db, "purge-war")
    db.commit()
    service = ClanWarService()
    war = service.create_war(db, _payload(target, fighters), leader)
    war_id = war.id
    AdminDeletionService().delete_war(db, war_id)
    db.commit()
    assert db.scalar(select(ClanWar).where(ClanWar.id == war_id)) is None
    assert db.get(User, fighters[0]) is not None
    assert service.get_war_readiness(db, clan.id, leader)["attack_points"]["available"] == 1
    assert target.status == "neutral"


def test_system_clan_cannot_be_purged(db):
    clan = Clan(name="System", is_admin_clan=True)
    db.add(clan)
    db.commit()
    with pytest.raises(HTTPException) as error:
        AdminDeletionService().delete_clan(db, clan.id)
    assert error.value.status_code == 409
