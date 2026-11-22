from app.models.clan import Clan, ClanMember
from app.models.operation import AdminAuditLog
from app.models.role import Role
from app.models.user import User
from app.services.external_identity_service import ExternalIdentityService
from app.services.war_service import ClanWarService


def make_user(db, user_id, username, role, claimed=True):
    user = User(
        id=user_id,
        username=username,
        email=f"{username}@example.com",
        hashed_password="unused",
        role=role,
        is_claimed=claimed,
    )
    db.add(user)
    db.flush()
    return user


def test_admin_can_approve_and_reject_identity_with_audit(db):
    admin_role = Role(name="admin")
    user_role = Role(name="user")
    db.add_all([admin_role, user_role])
    db.flush()
    admin = make_user(db, 1, "admin", admin_role)
    player = make_user(db, 2, "player", user_role)
    identity_service = ExternalIdentityService()
    identity = identity_service.observe(db, player, "player-uuid", "player")

    approved = identity_service.review_verification(
        db,
        target_user=player,
        reviewer=admin,
        decision="approve",
        reason="Ник проверен администратором",
    )
    assert approved.verification_status == "verified"
    assert approved.verified_at is not None

    approved.verification_status = "pending"
    db.commit()
    rejected = identity_service.review_verification(
        db,
        target_user=player,
        reviewer=admin,
        decision="reject",
        reason="Владелец не подтвердил аккаунт",
    )
    assert rejected.verification_status == "unverified"
    assert db.query(AdminAuditLog).count() == 2

    requested = identity_service.request_verification(db, player)
    assert requested.verification_status == "pending"


def test_unverified_players_do_not_reach_war_scoring(db):
    user_role = Role(name="user")
    db.add(user_role)
    db.flush()
    winner = make_user(db, 10, "winner", user_role)
    loser = make_user(db, 11, "loser", user_role)
    identity_service = ExternalIdentityService()
    identity_service.observe(db, winner, "winner-uuid", "winner")
    identity_service.observe(db, loser, "loser-uuid", "loser")

    clan_a = Clan(id=20, name="A", leader_id=winner.id)
    clan_b = Clan(id=21, name="B", leader_id=loser.id)
    db.add_all([clan_a, clan_b])
    db.flush()
    db.add_all(
        [
            ClanMember(user_id=winner.id, clan_id=clan_a.id),
            ClanMember(user_id=loser.id, clan_id=clan_b.id),
        ]
    )
    db.commit()

    war_service = ClanWarService()

    def must_not_load_active_wars(_db):
        raise AssertionError("Неподтвержденные игроки дошли до расчета войны")

    war_service.war_repo.get_active_wars = must_not_load_active_wars
    war_service.record_match_result(db, "winner", "loser")
