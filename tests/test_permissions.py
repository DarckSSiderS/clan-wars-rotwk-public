import pytest

from app.core.exceptions import InsufficientPermissionsException
from app.core.permissions import ClanPermission, require_clan_permission
from app.models.clan import Clan, ClanMember
from app.models.role import Role
from app.models.user import User


def make_user(db, username, role, user_id):
    user = User(
        id=user_id,
        username=username,
        email=f"{username}@example.test",
        hashed_password="unused",
        role=role,
    )
    db.add(user)
    return user


def test_clan_permissions_follow_role_matrix(db):
    admin_role = Role(name="admin", description="Admin")
    user_role = Role(name="user", description="User")
    db.add_all([admin_role, user_role])
    db.flush()

    leader = make_user(db, "leader", user_role, 1)
    trader = make_user(db, "trader", user_role, 2)
    warrior = make_user(db, "warrior", user_role, 3)
    admin = make_user(db, "admin", admin_role, 4)
    clan = Clan(id=1, name="Test clan", leader_id=leader.id)
    db.add(clan)
    db.flush()
    db.add_all(
        [
            ClanMember(clan_id=clan.id, user_id=leader.id, rank="Лидер"),
            ClanMember(clan_id=clan.id, user_id=trader.id, rank="Участник", is_trader=True),
            ClanMember(clan_id=clan.id, user_id=warrior.id, rank="Воин"),
        ]
    )
    db.commit()

    assert require_clan_permission(db, clan.id, leader, ClanPermission.DECLARE_WAR)[0] == clan
    assert require_clan_permission(db, clan.id, trader, ClanPermission.MANAGE_MARKET)[0] == clan
    assert require_clan_permission(db, clan.id, admin, ClanPermission.MANAGE_RELICS)[0] == clan

    with pytest.raises(InsufficientPermissionsException):
        require_clan_permission(db, clan.id, trader, ClanPermission.MANAGE_RELICS)
    with pytest.raises(InsufficientPermissionsException):
        require_clan_permission(db, clan.id, warrior, ClanPermission.DECLARE_WAR)
