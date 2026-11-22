import pytest

from app.core.campaign_rules import default_campaign_rule_values
from app.core.exceptions import InsufficientPermissionsException
from app.models.campaign import CampaignRuleSet
from app.models.clan import Clan, ClanMember
from app.models.role import Role
from app.models.user import User
from app.services.clan_service import ClanService


def _user(db, user_id, username, role):
    user = User(
        id=user_id,
        username=username,
        email=f"{username}@example.test",
        hashed_password="unused",
        role=role,
    )
    db.add(user)
    db.flush()
    return user


def test_leader_assigns_canonical_member_roles(db):
    role = Role(name="user")
    db.add(role)
    db.flush()
    leader = _user(db, 1, "leader", role)
    member_user = _user(db, 2, "member", role)
    clan = Clan(id=1, name="Clan", leader_id=leader.id)
    db.add(clan)
    db.flush()
    db.add_all(
        [
            ClanMember(
                clan_id=clan.id,
                user_id=leader.id,
                rank="Глава клана",
            ),
            ClanMember(
                clan_id=clan.id,
                user_id=member_user.id,
                rank="Салага",
            ),
        ]
    )
    db.commit()
    service = ClanService()

    trader = service.set_member_role(
        db,
        clan.id,
        member_user.id,
        "Торговец",
        leader,
    )
    assert trader.rank == "Торговец"
    assert trader.is_trader is True

    warrior = service.set_member_role(
        db,
        clan.id,
        member_user.id,
        "Воин",
        leader,
    )
    assert warrior.rank == "Воин"
    assert warrior.is_trader is False

    with pytest.raises(InsufficientPermissionsException):
        service.set_member_role(db, clan.id, leader.id, "Салага", leader)


def _warlord_clan(db):
    role = Role(name="user")
    db.add(role)
    db.flush()
    leader = _user(db, 10, "warlord-leader", role)
    first = _user(db, 11, "first-warlord", role)
    second = _user(db, 12, "second-warlord", role)
    clan = Clan(id=10, name="Warlord clan", leader_id=leader.id, level=1)
    db.add(clan)
    db.flush()
    db.add_all(
        [
            ClanMember(clan_id=clan.id, user_id=leader.id, rank="Глава клана"),
            ClanMember(clan_id=clan.id, user_id=first.id, rank="Воин"),
            ClanMember(clan_id=clan.id, user_id=second.id, rank="Торговец"),
            CampaignRuleSet(
                version=1,
                values=default_campaign_rule_values(),
                is_active=True,
                reason="test",
            ),
        ]
    )
    db.commit()
    return clan, leader, first, second


def test_leader_assigns_warlord_as_status_without_changing_member_role(db):
    clan, leader, first, _ = _warlord_clan(db)

    member = ClanService().set_member_warlord(
        db,
        clan.id,
        first.id,
        True,
        leader,
    )

    assert member.is_warlord is True
    assert member.rank == "Воин"


def test_clan_level_limits_number_of_warlords(db):
    clan, leader, first, second = _warlord_clan(db)
    service = ClanService()
    service.set_member_warlord(db, clan.id, first.id, True, leader)

    with pytest.raises(InsufficientPermissionsException):
        service.set_member_warlord(db, clan.id, second.id, True, leader)


def test_only_clan_leader_can_assign_warlord(db):
    clan, leader, first, second = _warlord_clan(db)

    with pytest.raises(InsufficientPermissionsException):
        ClanService().set_member_warlord(
            db,
            clan.id,
            second.id,
            True,
            first,
        )
