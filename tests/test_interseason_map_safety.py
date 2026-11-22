"""Чтение старой карты и прямые команды безопасны после завершения сезона."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.v1.territories import router
from app.core.exceptions import InsufficientPermissionsException
from app.database import get_db
from app.schemas.war import ClanWarCreate
from app.services.war_service import ClanWarService
from tests.test_legacy_economy_isolation import legacy_world, add_season  # noqa: F401


def client(db):
    app = FastAPI()
    app.include_router(router, prefix='/territories')
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_interseason_map_normalizes_null_lists_only_in_response(db, legacy_world):
    _, _, territories, _ = legacy_world
    add_season(db, status='completed', cycle=False)
    land = territories[0]
    land.adjacent_territory_ids = None
    land.trade_routes = None
    land.special_resources = None
    db.commit()
    response = client(db).get('/territories/')
    assert response.status_code == 200
    row = next(row for row in response.json() if row['id'] == land.id)
    assert row['adjacent_territory_ids'] == row['trade_routes'] == row['special_resources'] == []
    db.expire_all()
    assert land.adjacent_territory_ids is land.trade_routes is land.special_resources is None


def test_interseason_map_does_not_rewrite_old_war_projections(db, legacy_world):
    _, clans, territories, _ = legacy_world
    add_season(db, status='completed', cycle=False)
    land = territories[0]
    land.status = 'contested'
    land.attacking_clans = [clans[1]]
    db.commit()
    response = client(db).get('/territories/')
    assert response.status_code == 200
    row = next(row for row in response.json() if row['id'] == land.id)
    assert row['attacking_clans'] == row['defending_clans'] == []
    assert row['status'] == 'active'
    db.expire_all()
    assert land.status == 'contested'
    assert [clan.id for clan in land.attacking_clans] == [clans[1].id]


def test_direct_war_service_does_not_start_a_new_campaign(db, legacy_world):
    users, _, territories, _ = legacy_world
    add_season(db, status='completed', cycle=False)
    payload = ClanWarCreate(territory_id=territories[1].id, squad_member_ids=[users[0].id],
        warlord_user_id=users[0].id, expected_rule_version=1)
    with pytest.raises(InsufficientPermissionsException, match='Межсезонье'):
        ClanWarService().create_war(db, payload, users[0])
