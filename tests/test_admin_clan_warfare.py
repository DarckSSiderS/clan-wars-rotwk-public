from contextlib import contextmanager
from datetime import timedelta

from fastapi.testclient import TestClient

from app.config import settings
from app.core.campaign_rules import default_campaign_rule_values
from app.core.time import utc_now
from app.database import get_db
from app.main import app
from app.models.campaign import CampaignRuleSet
from app.models.clan import Clan, ClanMember, ClanMembershipPeriod
from app.models.clan_warfare import ClanLevelEvent
from app.models.external_identity import ExternalPlayerIdentity
from app.models.role import Role
from app.models.territory import Territory
from app.models.user import User
from app.schemas.war import ClanWarCreate
from app.services.session_service import SessionService
from app.services.war_service import ClanWarService


def _clan(db, suffix):
    joined_at = utc_now() - timedelta(days=30)
    leader = User(
        username=f"admin-war-leader-{suffix}",
        email=f"admin-war-leader-{suffix}@example.test",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
    )
    db.add(leader)
    db.flush()
    clan = Clan(
        name=f"Admin warfare clan {suffix}",
        leader_id=leader.id,
        base_influence=5000,
        territory_points=5000,
    )
    db.add(clan)
    db.flush()
    db.add(ClanMember(user_id=leader.id, clan_id=clan.id, rank="Глава клана"))
    fighters = []
    for index in range(5):
        fighter = User(
            username=f"admin-war-{suffix}-{index}",
            email=f"admin-war-{suffix}-{index}@example.test",
            hashed_password="unused",
            is_active=True,
            is_claimed=True,
        )
        db.add(fighter)
        db.flush()
        db.add_all([
            ClanMember(
                user_id=fighter.id,
                clan_id=clan.id,
                joined_at=joined_at,
                is_warlord=index == 0,
            ),
            ClanMembershipPeriod(
                user_id=fighter.id,
                clan_id=clan.id,
                started_at=joined_at,
                started_reason="test",
            ),
            ExternalPlayerIdentity(
                user_id=fighter.id,
                external_uuid=f"admin-private-uuid-{suffix}-{index}",
                current_nickname=f"Admin Nick {suffix} {index}",
                verification_status="verified",
            ),
        ])
        fighters.append(fighter)
    db.flush()
    return clan, leader, fighters


def _war_and_users(db):
    db.add(CampaignRuleSet(
        version=1,
        values=default_campaign_rule_values(),
        is_active=True,
        reason="admin warfare test",
    ))
    admin_role = Role(name="admin", description="Administrator")
    user_role = Role(name="admin-warfare-user", description="User")
    admin = User(
        username="admin-warfare-admin",
        email="admin-warfare-admin@example.test",
        hashed_password="unused",
        role=admin_role,
        is_active=True,
        is_claimed=True,
    )
    regular = User(
        username="admin-warfare-regular",
        email="admin-warfare-regular@example.test",
        hashed_password="unused",
        role=user_role,
        is_active=True,
        is_claimed=True,
    )
    db.add_all([admin_role, user_role, admin, regular])
    attacker, leader, fighters = _clan(db, "a")
    defender, _, _ = _clan(db, "b")
    target = Territory(
        name="Admin warfare target",
        region="Test",
        svg_path_data="M0 0",
        owner_clan_id=defender.id,
        status="active",
        required_influence=30,
    )
    db.add(target)
    db.commit()
    war = ClanWarService().create_war(
        db,
        ClanWarCreate(
            territory_id=target.id,
            squad_member_ids=[fighter.id for fighter in fighters],
            warlord_user_id=fighters[0].id,
            expected_rule_version=1,
        ),
        leader,
    )
    db.add(ClanLevelEvent(
        clan_id=attacker.id,
        previous_level=1,
        new_level=2,
        active_member_count=5,
        territory_count=1,
        influence=5000,
        campaign_rule_set_id=1,
        rule_version=1,
        reason="test_level_change",
        occurred_at=utc_now(),
    ))
    db.commit()
    return war, admin, regular, attacker


def _session_headers(db, user):
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


def test_admin_warfare_endpoint_is_private_and_returns_full_audit(db):
    war, admin, regular, attacker = _war_and_users(db)
    path = f"/api/v1/admin/clan-warfare/wars/{war.id}"

    with _client(db) as client:
        assert client.get(path).status_code == 401
        assert client.get(
            path,
            headers=_session_headers(db, regular),
        ).status_code == 403
        response = client.get(path, headers=_session_headers(db, admin))

    assert response.status_code == 200
    warfare = response.json()["admin_warfare"]
    assert warfare["campaign_rule_set_id"] == 1
    assert len(warfare["deployments"]) == 2
    attacker_deployment = next(
        item for item in warfare["deployments"] if item["clan_id"] == attacker.id
    )
    assert attacker_deployment["assigned_by_user_id"] == attacker.leader_id
    assert all(
        member["external_uuid_snapshot"].startswith("admin-private-uuid-")
        for member in attacker_deployment["members"]
    )
    spend = warfare["attack_point_spends"][0]
    assert spend["spent_at"] and spend["recover_at"]
    assert spend["level_snapshot"] == 1
    assert spend["capacity_snapshot"] == 1
    assert spend["rule_version"] == 1
    assert warfare["level_events"][0]["rule_version"] == 1
    assert any(
        entry["action"] == "war_deployment_created"
        for entry in warfare["audit_entries"]
    )
