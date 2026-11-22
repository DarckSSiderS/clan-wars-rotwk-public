import pytest

from app.core.exceptions import InsufficientPermissionsException
from app.models.clan import Clan, ClanMember
from app.models.clan_asset import ClanAsset
from app.models.diplomacy import ClanDiplomacyEvent, ClanDiplomaticRelation
from app.models.operation import AdminAuditLog
from app.models.role import Role
from app.models.territory import Territory
from app.models.user import User
from app.models.war import ClanWar, ClanWarParticipant
from app.schemas.clan import ClanApplicationCreate
from app.schemas.war import ClanWarCreate
from app.services.bootstrap_service import (
    ADMIN_CLAN_INITIAL_RESOURCES,
    ensure_admin_test_clan,
    ensure_default_admin,
)
from app.services.clan_service import ClanService
from app.services.war_service import ClanWarService


def add_tol_falas(db):
    territory = Territory(
        name="Тол-Фалас",
        region="gondor",
        description="Островной административный полигон.",
        svg_path_data="M 0 0 L 10 0 L 10 10 Z",
    )
    db.add(territory)
    db.commit()
    return territory


def test_admin_clan_bootstrap_claims_tol_falas(db):
    territory = add_tol_falas(db)

    ensure_default_admin(db)
    clan = ensure_admin_test_clan(db)
    clan.map_color = "#E63946"
    db.commit()
    clan = ensure_admin_test_clan(db)
    db.refresh(territory)

    assert clan.is_admin_clan is True
    assert clan.map_color is None
    assert territory.owner_clan_is_admin is True
    assert territory.owner_clan_map_color is None
    assert clan.leader.username == "clanwar"
    assert clan.leader.role.name == "admin"
    assert db.query(ClanMember).filter_by(
        clan_id=clan.id,
        user_id=clan.leader_id,
    ).one().rank == "Глава клана"
    assert territory.owner_clan_id == clan.id
    assert territory.is_playable is True
    assert territory.is_coastal is True
    assert territory.has_port is True
    assert territory.resource_type == "mithril"
    for resource, amount in ADMIN_CLAN_INITIAL_RESOURCES.items():
        assert getattr(clan, resource) == amount
    relics = db.query(ClanAsset).all()
    assert len(relics) == 15
    relic_prices = {relic.key: relic.gold_cost for relic in relics}
    assert relic_prices["royal_charter"] == 1900
    assert relic_prices["war_foundry"] == 2250
    assert relic_prices["mithril_standard"] == 2600
    assert all(
        all(level in (relic.description or "") for level in ("I", "II", "III"))
        for relic in relics
    )


def test_content_bootstrap_can_skip_test_admin_account(db):
    result = ensure_default_admin(db, create_account=False)

    assert result is None
    assert db.query(User).filter(User.username == "clanwar").count() == 0
    assert db.query(ClanAsset).count() > 0


def test_default_admin_bootstrap_promotes_darcks_and_demotes_legacy_admin(db):
    admin_role = Role(name="admin", description="Администратор")
    user_role = Role(name="user", description="Игрок")
    legacy_admin = User(
        username="Ar-Adunaim",
        email="legacy-admin@example.com",
        hashed_password="x",
        role=admin_role,
        is_active=True,
        is_claimed=True,
    )
    db.add_all([admin_role, user_role, legacy_admin])
    db.commit()

    primary_admin = ensure_default_admin(db)

    db.refresh(legacy_admin)
    assert primary_admin.username == "clanwar"
    assert primary_admin.role.name == "admin"
    assert primary_admin.level == 10
    assert primary_admin.experience == 32000
    assert legacy_admin.role.name == "user"


def test_admin_clan_rejects_applications_and_audits_appointments(db):
    add_tol_falas(db)
    clan = ensure_admin_test_clan(db)
    user_role = Role(name="user", description="Игрок")
    target = User(
        username="appointed-player",
        email="appointed@example.com",
        hashed_password="unused",
        role=user_role,
        is_active=True,
        is_claimed=True,
    )
    db.add_all([user_role, target])
    db.commit()

    service = ClanService()
    with pytest.raises(InsufficientPermissionsException) as error:
        service.create_clan_application(
            db,
            clan.id,
            ClanApplicationCreate(message="Возьмите меня"),
            target.id,
        )
    assert error.value.status_code == 403

    member = service.appoint_admin_clan_member(
        db,
        clan.id,
        target.id,
        clan.leader,
    )
    assert member.rank == "Воин"
    audit = db.query(AdminAuditLog).filter_by(
        action="admin_clan_member_appointed"
    ).one()
    assert audit.actor_user_id == clan.leader_id
    assert audit.after_data["user_id"] == target.id


def test_admin_can_reset_sandbox_resources_and_attack_turn(db):
    add_tol_falas(db)
    clan = ensure_admin_test_clan(db)
    clan.gold = 1
    clan.mithril = 0
    clan.next_attack_at = clan.created_at
    db.commit()

    reset = ClanService().reset_admin_clan_sandbox(
        db,
        clan.id,
        clan.leader,
    )

    assert reset.gold == ADMIN_CLAN_INITIAL_RESOURCES["gold"]
    assert reset.mithril == ADMIN_CLAN_INITIAL_RESOURCES["mithril"]
    assert reset.next_attack_at is None
    assert db.query(AdminAuditLog).filter_by(
        action="admin_clan_sandbox_reset"
    ).count() == 1


def test_tol_falas_cannot_be_attacked_and_does_not_consume_turn(db):
    territory = add_tol_falas(db)
    ensure_admin_test_clan(db)
    user_role = db.query(Role).filter(Role.name == "user").first()
    if user_role is None:
        user_role = Role(name="user", description="Игрок")
        db.add(user_role)
        db.flush()
    leader = User(
        username="attacking-leader",
        email="attacker@example.com",
        hashed_password="unused",
        role=user_role,
        is_active=True,
        is_claimed=True,
    )
    attacker = Clan(
        name="Проверочный атакующий клан",
        leader=leader,
        territory_points=5000,
    )
    db.add_all([leader, attacker])
    db.flush()
    db.add(ClanMember(
        clan_id=attacker.id,
        user_id=leader.id,
        rank="Глава клана",
    ))
    db.commit()

    with pytest.raises(InsufficientPermissionsException) as error:
        ClanWarService().create_war(
            db,
            ClanWarCreate(
                territory_id=territory.id,
                squad_member_ids=[leader.id],
                warlord_user_id=leader.id,
                expected_rule_version=1,
            ),
            leader,
        )

    db.refresh(attacker)
    assert "административную территорию" in error.value.detail
    assert attacker.next_attack_at is None


def test_deleted_clan_is_archived_without_losing_war_map_or_score(db):
    user_role = Role(name="user", description="Игрок")
    leader = User(
        username="deletable-leader",
        email="deletable@example.com",
        hashed_password="unused",
        role=user_role,
        is_active=True,
        is_claimed=True,
    )
    clan = Clan(
        name="Удаляемый клан",
        leader=leader,
        territory_points=500,
    )
    rival = Clan(name="Клан-соперник")
    territory = Territory(
        name="Удаляемая война",
        region="gondor",
        description="Проверка удаления клана с активной войной.",
        svg_path_data="M 0 0 L 20 0 L 20 20 Z",
    )
    db.add_all([user_role, leader, clan, rival, territory])
    db.flush()
    territory.owner_clan_id = clan.id
    db.add(ClanMember(
        clan_id=clan.id,
        user_id=leader.id,
        rank="Глава клана",
    ))
    active_war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=clan.id,
        war_type="neutral_capture",
        status="active",
        required_wins=5,
    )
    historical_war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=clan.id,
        defending_clan_id=rival.id,
        winner_clan_id=clan.id,
        war_type="territory_attack",
        status="completed",
        required_wins=5,
    )
    db.add_all([active_war, historical_war])
    relation = ClanDiplomaticRelation(
        clan_low_id=min(clan.id, rival.id),
        clan_high_id=max(clan.id, rival.id),
        status="allied",
    )
    db.add(relation)
    db.flush()
    db.add(ClanDiplomacyEvent(
        relation_id=relation.id,
        actor_clan_id=clan.id,
        previous_status="neutral",
        new_status="allied",
    ))
    db.add(ClanWarParticipant(
        war_id=historical_war.id,
        clan_id=clan.id,
        user_id=leader.id,
        is_active=True,
    ))
    db.commit()

    clan_id = clan.id
    assert ClanService().delete_clan(db, clan_id) is True

    archived = db.query(Clan).filter(Clan.id == clan_id).one()
    assert archived.is_deleted is True
    assert archived.is_recruiting is False
    assert archived.deleted_at is not None
    assert archived.leader_id is None
    assert archived.territory_points == 500
    assert db.query(ClanMember).filter(ClanMember.clan_id == clan_id).count() == 0
    preserved_war = db.query(ClanWar).filter(ClanWar.id == active_war.id).one()
    assert preserved_war.status == "canceled"
    assert preserved_war.ended_at is not None
    preserved_history = db.query(ClanWar).filter(ClanWar.id == historical_war.id).one()
    assert preserved_history.status == "completed"
    assert db.query(ClanWarParticipant).filter_by(
        war_id=historical_war.id,
        clan_id=clan_id,
    ).one().is_active is True
    preserved_territory = db.query(Territory).filter(Territory.id == territory.id).one()
    assert preserved_territory.owner_clan_id == clan_id
    assert preserved_territory.status == "active"
    preserved_relation = db.query(ClanDiplomaticRelation).one()
    assert preserved_relation.status == "neutral"
    assert db.query(ClanDiplomacyEvent).filter_by(relation_id=preserved_relation.id).count() == 2
    assert ClanService().get_clans(db) == [rival]


def test_war_listing_cancels_active_war_against_already_archived_clan(db):
    attacker = Clan(name="Живой клан")
    archived_defender = Clan(name="Архивный защитник", is_deleted=True)
    participant_user = User(
        username="orphan-war-attacker",
        email="orphan-war-attacker@example.com",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
    )
    territory = Territory(
        name="Осиротевшая война",
        region="gondor",
        description="Проверка очистки войны с архивным защитником.",
        svg_path_data="M 0 0 L 20 0 L 20 20 Z",
        status="contested",
    )
    db.add_all([attacker, archived_defender, participant_user, territory])
    db.flush()
    territory.owner_clan_id = archived_defender.id
    territory.attacking_clans.append(attacker)
    territory.defending_clans.append(archived_defender)
    war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=attacker.id,
        defending_clan_id=archived_defender.id,
        war_type="territory_attack",
        status="active",
        required_wins=5,
    )
    db.add(war)
    db.flush()
    participant = ClanWarParticipant(
        war_id=war.id,
        clan_id=attacker.id,
        user_id=participant_user.id,
        is_active=True,
    )
    db.add(participant)
    db.commit()

    assert ClanWarService().get_active_wars(db) == []

    db.refresh(war)
    db.refresh(participant)
    db.refresh(territory)
    assert war.status == "canceled"
    assert war.ended_at is not None
    assert participant.is_active is False
    assert territory.status == "active"
    assert attacker not in territory.attacking_clans
    assert archived_defender not in territory.defending_clans


def test_closed_clan_rejects_applications(db):
    clan = Clan(name="Закрытый клан", is_recruiting=False)
    user = User(
        username="closed-clan-applicant",
        email="closed-clan-applicant@example.com",
        hashed_password="unused",
        is_active=True,
        is_claimed=True,
    )
    db.add_all([clan, user])
    db.commit()

    with pytest.raises(InsufficientPermissionsException, match="не ведёт набор"):
        ClanService().create_clan_application(
            db,
            clan.id,
            ClanApplicationCreate(message="Возьмите меня"),
            user.id,
        )
