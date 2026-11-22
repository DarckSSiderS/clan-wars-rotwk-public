import asyncio
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi import UploadFile
from PIL import Image

from app.api.v1.admin import (
    AdminReasonRequest,
    AdminTerritoryUpdate,
    AdminUserRoleUpdate,
    assign_admin_title,
    ClanEconomyUpdate,
    WarExtensionRequest,
    WarMatchReviewRequest,
    cancel_admin_war,
    extend_admin_war,
    get_admin_overview,
    get_admin_users,
    create_admin_title,
    remove_admin_title,
    get_admin_territories,
    review_admin_war_match,
    update_admin_territory,
    update_admin_user_role,
    update_clan_economy,
)
from app.api.v1.users import get_user_stats
from app.api.v1.users import get_public_identity_directory, get_public_profile_overview
from app.models.clan import Clan, ClanMember, ClanMembershipPeriod
from app.models.external_identity import ExternalPlayerIdentity
from app.models.match import Match, MatchParticipant
from app.models.operation import AdminAuditLog, ResourceLedgerEntry
from app.models.role import Role
from app.models.territory import Territory
from app.models.title import Title, UserTitle
from app.models.user import User
from app.models.war import ClanWar, ClanWarMatchResult
from app.services.war_service import ClanWarService


def _admin(db):
    role = Role(name="admin", description="Администратор")
    user = User(
        username="dashboard-admin",
        email="dashboard-admin@example.com",
        hashed_password="unused",
        role=role,
        is_active=True,
        is_claimed=True,
    )
    db.add_all([role, user])
    db.flush()
    return user


def test_admin_economy_update_writes_ledger_and_audit(db):
    admin = _admin(db)
    clan = Clan(
        name="Клан казначеев",
        gold=100,
        resources=100,
        iron=5,
        wood=7,
        food=3,
        mithril=1,
        base_influence=100,
        territory_points=100,
    )
    db.add(clan)
    db.commit()

    result = update_clan_economy(
        clan.id,
        ClanEconomyUpdate(gold=175, influence=140, reason="Проверка панели"),
        admin,
        db,
    )

    db.refresh(clan)
    assert result["clan"]["gold"] == 175
    assert clan.resources == 175
    assert clan.territory_points == 140
    assert clan.base_influence == 140
    entries = db.query(ResourceLedgerEntry).order_by(ResourceLedgerEntry.resource).all()
    assert [(item.resource, item.amount) for item in entries] == [("gold", 75), ("influence", 40)]
    audit = db.query(AdminAuditLog).filter_by(action="clan_economy_updated").one()
    assert audit.actor_user_id == admin.id
    assert audit.reason == "Проверка панели"
    assert audit.before_data["gold"] == 100
    assert audit.after_data["gold"] == 175


def test_admin_overview_counts_only_claimed_registered_users(db):
    admin = _admin(db)
    role = db.query(Role).filter(Role.name == "admin").one()
    claimed = User(username="claimed", email="claimed@example.com", hashed_password="x", role=role, is_claimed=True, is_active=True)
    imported = User(username="imported", email="imported@example.com", hashed_password="x", role=role, is_claimed=False, is_active=False)
    clan = Clan(name="Обычный клан", leader=claimed)
    archived_clan = Clan(name="Архивный клан", is_deleted=True)
    db.add_all([claimed, imported, clan, archived_clan])
    db.flush()
    db.add(ClanMember(user_id=claimed.id, clan_id=clan.id, rank="Глава клана"))
    db.commit()

    overview = get_admin_overview(admin, db)

    assert overview["users"]["registered"] == 2
    assert overview["users"]["active"] == 2
    assert overview["clans"]["total"] == 1
    assert overview["clans"]["members"] == 1


def test_admin_can_grant_and_revoke_admin_role_with_audit(db):
    admin = _admin(db)
    user_role = Role(name="user", description="Игрок")
    target = User(
        username="future-admin",
        email="future-admin@example.com",
        hashed_password="x",
        role=user_role,
        is_active=True,
        is_claimed=True,
    )
    db.add_all([user_role, target])
    db.commit()

    granted = update_admin_user_role(
        target.id,
        AdminUserRoleUpdate(is_admin=True, reason="Назначение помощника"),
        admin,
        db,
    )
    db.refresh(target)
    assert granted["is_admin"] is True
    assert target.role.name == "admin"
    assert any(item["username"] == target.username and item["is_admin"] for item in get_admin_users(admin, db)["users"])

    revoked = update_admin_user_role(
        target.id,
        AdminUserRoleUpdate(is_admin=False, reason="Завершение проверки"),
        admin,
        db,
    )
    db.refresh(target)
    assert revoked["is_admin"] is False
    assert target.role.name == "user"
    audit = db.query(AdminAuditLog).filter_by(action="user_admin_role_updated").all()
    assert len(audit) == 2
    assert audit[0].before_data["role"] == "user"
    assert audit[0].after_data["role"] == "admin"


def test_admin_cannot_grant_role_to_unclaimed_profile_or_revoke_self(db):
    admin = _admin(db)
    user_role = Role(name="user", description="Игрок")
    imported = User(
        username="imported-profile",
        email="imported-profile@example.com",
        hashed_password="x",
        role=user_role,
        is_active=False,
        is_claimed=False,
    )
    db.add_all([user_role, imported])
    db.commit()

    with pytest.raises(HTTPException) as unclaimed_error:
        update_admin_user_role(
            imported.id,
            AdminUserRoleUpdate(is_admin=True, reason="Нельзя назначать"),
            admin,
            db,
        )
    assert unclaimed_error.value.status_code == 400

    with pytest.raises(HTTPException) as self_error:
        update_admin_user_role(
            admin.id,
            AdminUserRoleUpdate(is_admin=False, reason="Проверка защиты"),
            admin,
            db,
        )
    assert self_error.value.status_code == 400


def test_primary_admin_cannot_be_demoted_by_another_admin(db):
    admin = _admin(db)
    admin_role = db.query(Role).filter(Role.name == "admin").one()
    primary_admin = User(
        username="darcks",
        email="clanwar@example.com",
        hashed_password="x",
        role=admin_role,
        is_active=True,
        is_claimed=True,
    )
    db.add(primary_admin)
    db.commit()

    with pytest.raises(HTTPException) as error:
        update_admin_user_role(
            primary_admin.id,
            AdminUserRoleUpdate(is_admin=False, reason="Проверка защиты главного администратора"),
            admin,
            db,
        )

    assert error.value.status_code == 400
    db.refresh(primary_admin)
    assert primary_admin.role.name == "admin"


def test_admin_user_search_filters_by_title_without_loading_full_directory(db):
    admin = _admin(db)
    role = Role(name="user", description="Игрок")
    marshal = Title(
        name="Маршал",
        description="Командующий",
        image_url="/images/titles/marshal.webp",
        is_active=True,
    )
    scout = Title(
        name="Разведчик",
        description="Искатель",
        image_url="/images/titles/scout.webp",
        is_active=True,
    )
    users = [
        User(
            username=username,
            email=f"{username.lower()}@example.test",
            hashed_password="x",
            role=role,
            is_claimed=True,
            is_active=True,
        )
        for username in ("AlphaMarshal", "AlphaScout", "BetaPlayer")
    ]
    db.add_all([role, marshal, scout, *users])
    db.flush()
    db.add_all(
        [
            UserTitle(user_id=users[0].id, title_id=marshal.id, assigned_by_user_id=admin.id),
            UserTitle(user_id=users[1].id, title_id=scout.id, assigned_by_user_id=admin.id),
        ]
    )
    db.commit()

    searched = get_admin_users(admin, db, search="alpha", limit=10)
    assert [item["username"] for item in searched["users"]] == [
        "AlphaMarshal",
        "AlphaScout",
    ]

    with_marshal = get_admin_users(
        admin,
        db,
        title_filter="with",
        title_id=marshal.id,
        limit=10,
    )
    assert [item["username"] for item in with_marshal["users"]] == ["AlphaMarshal"]

    without_marshal = get_admin_users(
        admin,
        db,
        title_filter="without",
        title_id=marshal.id,
        limit=2,
    )
    assert [item["username"] for item in without_marshal["users"]] == [
        "AlphaScout",
        "BetaPlayer",
    ]


def test_admin_creates_assigns_and_removes_public_title(db, tmp_path, monkeypatch):
    admin = _admin(db)
    user_role = Role(name="user", description="Игрок")
    target = User(
        username="title-holder",
        email="title-holder@example.com",
        hashed_password="x",
        role=user_role,
        is_active=True,
        is_claimed=True,
    )
    db.add_all([user_role, target])
    db.commit()

    monkeypatch.setattr("app.api.v1.admin.settings.UPLOAD_DIR", str(tmp_path))
    source = io.BytesIO()
    Image.new("RGBA", (320, 180), (190, 35, 35, 255)).save(source, format="PNG")
    upload = UploadFile(filename="marshal.png", file=io.BytesIO(source.getvalue()))
    upload.headers = {"content-type": "image/png"}

    created = asyncio.run(create_admin_title(
        name="Маршал",
        description="Командующий армиями клана",
        name_en="Marshal",
        description_en="Commander of the clan armies",
        name_de="Marschall",
        description_de="Befehlshaber der Clanarmeen",
        image=upload,
        current_admin=admin,
        db=db,
    ))
    title = db.query(Title).filter_by(id=created["id"]).one()
    assert title.image_url.startswith("/images/titles/")
    assert (tmp_path / "titles" / title.image_url.rsplit("/", 1)[-1]).is_file()

    assigned = assign_admin_title(title.id, target.id, admin, db)
    assert assigned["assigned"] is True
    directory = get_public_identity_directory(db)
    identity = next(item for item in directory["players"] if item["username"] == target.username)
    assert identity["is_admin"] is False
    assert identity["titles"][0]["name"] == "Маршал"

    profile = asyncio.run(get_public_profile_overview(target.username, db))
    assert profile["user"]["titles"][0]["description"] == "Командующий армиями клана"

    removed = remove_admin_title(title.id, target.id, admin, db)
    assert removed["assigned"] is False
    assert db.query(UserTitle).filter_by(user_id=target.id, title_id=title.id).count() == 0


def test_clan_member_stats_return_separate_elo_for_each_patch(db):
    role = Role(name="user", description="Игрок")
    user = User(username="EloPlayer", email="elo@example.com", hashed_password="x", role=role, is_claimed=True, is_active=True)
    clan = Clan(name="Клан Elo", leader=user, preferred_patch="all")
    db.add_all([role, user, clan])
    db.flush()
    db.add(ClanMember(user_id=user.id, clan_id=clan.id, rank="Глава клана"))

    for index, (patch, elo) in enumerate((("patch_202", 1375), ("ennorath", 1210)), start=1):
        match = Match(
            match_id=f"elo-{index}",
            winner_player=user.username,
            winner_faction="Men",
            loser_player=f"Opponent{index}",
            loser_faction="Mordor",
            match_date=datetime(2026, 7, index, tzinfo=timezone.utc),
            rating_patch_family=patch,
        )
        match.participants.append(MatchParticipant(nickname=user.username, team=1, is_winner=True, elo=elo))
        db.add(match)
    db.commit()

    stats = asyncio.run(get_user_stats(user.id, clan.id, db, user))

    assert stats["elo_patch"] == "all"
    assert stats["elo_ratings"] == {"ennorath": 1210, "patch_202": 1375}


def _active_war(db, admin):
    role = db.query(Role).filter(Role.name == "admin").one()
    attacker = User(username="war-attacker", email="war-attacker@example.com", hashed_password="x", role=role, is_claimed=True, is_active=True)
    defender = User(username="war-defender", email="war-defender@example.com", hashed_password="x", role=role, is_claimed=True, is_active=True)
    attacking_clan = Clan(name="Атакующие", leader=attacker, next_attack_at=datetime.now(timezone.utc) + timedelta(days=3))
    defending_clan = Clan(name="Защитники", leader=defender)
    db.add_all([attacker, defender, attacking_clan, defending_clan])
    db.flush()
    played_at = datetime.now(timezone.utc) - timedelta(hours=1)
    for user, clan in ((attacker, attacking_clan), (defender, defending_clan)):
        db.add(ExternalPlayerIdentity(user_id=user.id, external_uuid=f"uuid-{user.username}", current_nickname=user.username, verification_status="verified"))
        db.add(ClanMembershipPeriod(user_id=user.id, clan_id=clan.id, started_at=played_at - timedelta(days=1)))
    territory = Territory(name="Спорная земля", region="test", svg_path_data="M 0 0", owner_clan_id=defending_clan.id, status="contested")
    db.add(territory)
    db.flush()
    war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=attacking_clan.id,
        defending_clan_id=defending_clan.id,
        war_type="territory_attack",
        status="active",
        started_at=played_at - timedelta(hours=1),
        ends_at=datetime.now(timezone.utc) + timedelta(days=4),
    )
    match = Match(
        match_id="admin-war-match",
        winner_player=attacker.username,
        winner_faction="Люди",
        loser_player=defender.username,
        loser_faction="Мордор",
        match_date=played_at,
        duration="00:12:00",
        game_mode="1 versus 1",
        gamemode_name="1 versus 1",
        elo_delta=12,
        is_valid=True,
        map_name="Форност",
        patch_version="2.02 v9",
    )
    db.add_all([war, match])
    db.commit()
    ClanWarService().record_match_result(db, attacker.username, defender.username, played_at, match=match)
    return war, attacking_clan, defending_clan, territory


def test_admin_match_override_survives_recalculation_and_can_return_to_automatic(db):
    admin = _admin(db)
    war, _, _, _ = _active_war(db, admin)
    result = db.query(ClanWarMatchResult).one()
    assert result.is_counted is True

    review_admin_war_match(
        war.id,
        result.id,
        WarMatchReviewRequest(mode="exclude", reason="Повреждённый реплей"),
        admin,
        db,
    )
    ClanWarService().recalculate_active_war(db, war.id)
    db.refresh(result)
    assert result.admin_override is False
    assert result.is_counted is False
    assert result.rejection_reason.startswith("Исключено администратором")

    review_admin_war_match(
        war.id,
        result.id,
        WarMatchReviewRequest(mode="automatic", reason="Повторная проверка данных"),
        admin,
        db,
    )
    db.refresh(result)
    assert result.admin_override is None
    assert result.is_counted is True
    assert db.query(AdminAuditLog).filter_by(action="war_match_reviewed").count() == 2


def test_admin_can_extend_and_cancel_war_with_attack_refund(db):
    admin = _admin(db)
    war, attacker, _, territory = _active_war(db, admin)
    original_end = war.ends_at

    extend_admin_war(
        war.id,
        WarExtensionRequest(hours=24, reason="Разбор спорного матча"),
        admin,
        db,
    )
    db.refresh(war)
    assert war.ends_at >= original_end + timedelta(hours=23, minutes=59)

    cancel_admin_war(
        war.id,
        AdminReasonRequest(reason="Тестовая война создана ошибочно"),
        admin,
        db,
    )
    db.refresh(war)
    db.refresh(attacker)
    db.refresh(territory)
    assert war.status == "canceled"
    assert attacker.next_attack_at is None
    assert territory.status == "active"
    assert db.query(AdminAuditLog).filter_by(action="war_extended").count() == 1
    assert db.query(AdminAuditLog).filter_by(action="war_canceled").count() == 1


def test_admin_territory_editor_updates_owner_economy_and_audit(db):
    admin = _admin(db)
    clan = Clan(name="Новый владелец", base_influence=100, territory_points=100)
    territory = Territory(
        name="Земля для редактора",
        region="test",
        svg_path_data="M 1 1",
        resource_wealth=2,
        influence_value=10,
        required_influence=30,
        resource_type="iron",
        status="neutral",
    )
    db.add_all([clan, territory])
    db.commit()

    response = update_admin_territory(
        territory.id,
        AdminTerritoryUpdate(
            owner_clan_id=clan.id,
            resource_wealth=8,
            population=5000,
            influence_value=45,
            required_influence=250,
            development_level=4,
            fortifications=3,
            offense_level=2,
            is_coastal=True,
            has_port=True,
            port_level=3,
            fleet_level=2,
            reason="Подготовка территории к первой кампании",
        ),
        admin,
        db,
    )

    db.refresh(territory)
    db.refresh(clan)
    assert response["territory"]["owner_clan_name"] == clan.name
    assert territory.owner_clan_id == clan.id
    assert territory.status == "active"
    assert territory.resource_wealth == 8
    assert territory.required_influence == 250
    assert territory.strategic_value == 3.0
    assert clan.territory_points == 145
    ledger = db.query(ResourceLedgerEntry).filter_by(
        action="territory_influence_gained",
    ).one()
    assert ledger.actor_user_id == admin.id
    audit = db.query(AdminAuditLog).filter_by(
        action="territory_parameters_updated",
    ).one()
    assert audit.reason == "Подготовка территории к первой кампании"
    assert audit.before_data["owner_clan_id"] is None
    assert audit.after_data["owner_clan_id"] == clan.id
    assert len(get_admin_territories(admin, db)["territories"]) == 1


def test_admin_cannot_change_territory_owner_during_active_war(db):
    admin = _admin(db)
    war, attacking_clan, _, territory = _active_war(db, admin)

    with pytest.raises(HTTPException) as error:
        update_admin_territory(
            territory.id,
            AdminTerritoryUpdate(
                owner_clan_id=attacking_clan.id,
                reason="Попытка смены владельца во время войны",
            ),
            admin,
            db,
        )

    assert error.value.status_code == 409
    assert "активную войну" in error.value.detail
    db.refresh(war)
    assert war.status == "active"
