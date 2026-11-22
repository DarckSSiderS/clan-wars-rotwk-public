from datetime import timedelta

from app.core.campaign_rules import default_campaign_rule_values
from app.core.time import as_utc, utc_now
from app.models.campaign import CampaignRuleSet
from app.models.clan import Clan, ClanMember, ClanMembershipPeriod
from app.models.external_identity import ExternalPlayerIdentity
from app.models.role import Role
from app.models.territory import Territory
from app.models.user import User
from app.models.war import ClanWar, ClanWarParticipant
from app.schemas.war import ClanWarCreate
from app.services.war_service import ClanWarService
from app.api.v1.admin_clan_warfare import get_admin_clan_warfare_war


def _clan(db, suffix, *, count=6):
    joined_at = utc_now() - timedelta(days=30)
    leader = User(
        username=f"leader-{suffix}",
        email=f"leader-{suffix}@example.test",
        hashed_password="x",
    )
    db.add(leader)
    db.flush()
    clan = Clan(
        name=f"Clan {suffix}",
        leader_id=leader.id,
        base_influence=5000,
        territory_points=5000,
        avatar_url=f"/{suffix}.png",
        map_color="#112233" if suffix == "a" else "#445566",
    )
    db.add(clan)
    db.flush()
    db.add(ClanMember(user_id=leader.id, clan_id=clan.id, rank="Глава клана"))
    fighters = []
    for index in range(count):
        user = User(
            username=f"{suffix}-fighter-{index}",
            email=f"{suffix}-fighter-{index}@example.test",
            hashed_password="x",
        )
        db.add(user)
        db.flush()
        db.add_all(
            [
                ClanMember(
                    user_id=user.id,
                    clan_id=clan.id,
                    joined_at=joined_at,
                    is_warlord=index == 0,
                ),
                ClanMembershipPeriod(
                    user_id=user.id,
                    clan_id=clan.id,
                    started_at=joined_at,
                    started_reason="test",
                ),
                ExternalPlayerIdentity(
                    user_id=user.id,
                    external_uuid=f"uuid-{suffix}-{index}",
                    current_nickname=f"Nick {suffix} {index}",
                    verification_status="verified",
                ),
            ]
        )
        fighters.append(user)
    db.flush()
    return clan, leader, fighters


def _war(db):
    db.add(
        CampaignRuleSet(
            version=1,
            values=default_campaign_rule_values(),
            is_active=True,
            reason="test",
        )
    )
    attacker, leader, attackers = _clan(db, "a")
    defender, _, defenders = _clan(db, "b")
    target = Territory(
        name="Occupied",
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
            squad_member_ids=[user.id for user in attackers[:5]],
            warlord_user_id=attackers[0].id,
            expected_rule_version=1,
        ),
        leader,
    )
    return war, attacker, attackers, defender, defenders


def test_public_war_details_include_complete_squad_and_whole_clan_groups(db):
    war, attacker, attackers, defender, defenders = _war(db)

    details = ClanWarService().serialize_war(db, war)

    assert details["deployment_tracking"] is True
    groups = {group["clan_id"]: group for group in details["side_groups"]}
    assert groups[attacker.id]["role"] == "attacker"
    assert groups[attacker.id]["scope"] == "squad"
    assert groups[attacker.id]["member_count"] == 5
    assert len(groups[attacker.id]["members"]) == 5
    assert groups[defender.id]["role"] == "defender"
    assert groups[defender.id]["scope"] == "whole_clan"
    assert groups[defender.id]["member_count"] == len(defenders)
    assert len(groups[defender.id]["members"]) == len(defenders)
    assert all(
        "external_uuid_snapshot" not in member
        for group in groups.values()
        for member in group["members"]
    )


def test_squad_history_keeps_member_who_left_after_assignment(db):
    war, attacker, attackers, _, _ = _war(db)
    departed = attackers[0]
    member = db.query(ClanMember).filter_by(user_id=departed.id).one()
    period = (
        db.query(ClanMembershipPeriod)
        .filter_by(user_id=departed.id, clan_id=attacker.id)
        .one()
    )
    period.ended_at = utc_now() - timedelta(seconds=1)
    db.delete(member)
    db.commit()

    details = ClanWarService().serialize_war(db, war)
    group = next(
        group for group in details["side_groups"] if group["clan_id"] == attacker.id
    )
    row = next(member for member in group["members"] if member["user_id"] == departed.id)

    assert group["member_count"] == 5
    assert row["status_code"] == "left_clan"
    assert row["membership_ended_at"] == as_utc(period.ended_at)


def test_completed_whole_clan_group_uses_membership_period_history(db):
    war, attacker, _, defender, _ = _war(db)
    war.started_at = utc_now() - timedelta(hours=1)
    late = User(
        username="late-defender",
        email="late-defender@example.test",
        hashed_password="x",
    )
    db.add(late)
    db.flush()
    joined_at = war.started_at + timedelta(minutes=10)
    db.add(
        ClanMembershipPeriod(
            user_id=late.id,
            clan_id=defender.id,
            started_at=joined_at,
            started_reason="joined_during_war",
        )
    )
    service = ClanWarService()
    service._complete_war(db, war, attacker.id)

    details = service.serialize_war(db, war)
    group = next(
        group for group in details["side_groups"] if group["clan_id"] == defender.id
    )
    row = next(member for member in group["members"] if member["user_id"] == late.id)

    assert row["status_code"] == "joined_during_war"
    assert row["membership_started_at"] == joined_at


def test_member_metrics_are_returned_without_truncating_the_group(db):
    war, attacker, attackers, _, _ = _war(db)
    participant = (
        db.query(ClanWarParticipant)
        .filter_by(war_id=war.id, user_id=attackers[0].id)
        .one()
    )
    participant.wins = 2
    participant.losses = 1
    participant.war_points = 12.5
    db.commit()

    group = next(
        group
        for group in ClanWarService().serialize_war(db, war)["side_groups"]
        if group["clan_id"] == attacker.id
    )
    row = next(member for member in group["members"] if member["user_id"] == attackers[0].id)

    assert (row["matches"], row["wins"], row["losses"], row["points"]) == (
        3,
        2,
        1,
        12.5,
    )


def test_legacy_war_does_not_invent_deployment_history(db):
    attacker, _, _ = _clan(db, "legacy")
    target = Territory(name="Legacy", region="Test", svg_path_data="M9 0")
    db.add(target)
    db.flush()
    war = ClanWar(
        territory_id=target.id,
        attacking_clan_id=attacker.id,
        war_type="neutral_capture",
        status="active",
        scoring_version="elo_team_v2",
    )
    db.add(war)
    db.commit()

    details = ClanWarService().serialize_war(db, war)

    assert details["deployment_tracking"] is False
    assert details["side_groups"] == []


def test_admin_warfare_details_include_private_snapshot_uuid(db):
    war, _, _, _, _ = _war(db)
    role = Role(name="admin", description="Admin")
    admin = User(
        username="war-admin",
        email="war-admin@example.test",
        hashed_password="x",
        role=role,
    )
    db.add_all([role, admin])
    db.commit()

    details = get_admin_clan_warfare_war(war.id, db, admin)

    private_members = details["admin_warfare"]["deployments"][0]["members"]
    assert private_members
    assert private_members[0]["external_uuid_snapshot"].startswith("uuid-")
