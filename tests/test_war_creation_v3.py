from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core.campaign_rules import default_campaign_rule_values
from app.models.campaign import CampaignRuleSet
from app.models.clan import Clan, ClanMember, ClanMembershipPeriod
from app.models.clan_warfare import ClanAttackPointSpend
from app.models.external_identity import ExternalPlayerIdentity
from app.models.territory import Territory
from app.models.user import User
from app.models.war import ClanWar
from app.models.war_deployment import WarDeployment, WarDeploymentMember
from app.schemas.war import ClanWarCreate
from app.services.clan_economy_service import ClanEconomyService
from app.services.clan_service import ClanService
from app.services.war_service import ClanWarService


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def _rules(db):
    row = CampaignRuleSet(
        version=1,
        values=default_campaign_rule_values(),
        is_active=True,
        reason="test",
    )
    db.add(row)
    db.flush()
    return row


def _clan(db, suffix, *, member_count=5):
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
    )
    db.add(clan)
    db.flush()
    db.add(
        ClanMember(
            user_id=leader.id,
            clan_id=clan.id,
            rank="Глава клана",
            joined_at=NOW - timedelta(days=60),
        )
    )
    fighter_ids = []
    for index in range(member_count):
        user = User(
            username=f"fighter-{suffix}-{index}",
            email=f"fighter-{suffix}-{index}@example.test",
            hashed_password="x",
        )
        db.add(user)
        db.flush()
        db.add_all(
            [
                ClanMember(
                    user_id=user.id,
                    clan_id=clan.id,
                    joined_at=NOW - timedelta(days=30),
                    is_warlord=index == 0,
                ),
                ClanMembershipPeriod(
                    user_id=user.id,
                    clan_id=clan.id,
                    started_at=NOW - timedelta(days=30),
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
        fighter_ids.append(user.id)
    db.flush()
    return clan, leader, fighter_ids


def _territory(db, suffix, **values):
    territory = Territory(
        name=f"Territory {suffix}",
        region="Test",
        svg_path_data=f"M{suffix} 0",
        required_influence=30,
        **values,
    )
    db.add(territory)
    db.flush()
    return territory


def _payload(target, member_ids, *, source=None, version=1):
    return ClanWarCreate(
        territory_id=target.id,
        source_territory_id=source.id if source else None,
        squad_member_ids=member_ids,
        warlord_user_id=member_ids[0],
        expected_rule_version=version,
    )


def test_new_neutral_war_is_v3_with_snapshot_deployment_and_spend(db):
    rule = _rules(db)
    clan, leader, fighters = _clan(db, "a")
    target = _territory(db, "neutral")
    db.commit()

    war = ClanWarService().create_war(db, _payload(target, fighters), leader)

    assert war.scoring_version == "elo_team_v3_squads"
    assert war.campaign_rule_set_id == rule.id
    assert war.rules_snapshot["WAR_DURATION_HOURS"] == 60
    assert war.ends_at - war.started_at == timedelta(hours=60)
    assert len(war.deployments) == 1
    assert war.deployments[0].eligibility_scope == "squad"
    assert war.deployments[0].warlord_user_id == fighters[0]
    assert war.deployments[0].warlord_username_snapshot == "fighter-a-0"
    assert len(war.deployments[0].members) == 5
    assert len(war.attack_point_spends) == 1
    assert war.attack_point_spends[0].recover_at > war.attack_point_spends[0].spent_at
    spend = war.attack_point_spends[0]
    assert spend.recover_at - spend.spent_at == timedelta(hours=60)


def test_attack_archived_owner_creates_persistent_neutral_capture(db):
    _rules(db)
    clan, leader, fighters = _clan(db, "archived-target")
    archived = Clan(name="Archived owner", is_deleted=True)
    db.add(archived)
    db.flush()
    target = _territory(db, "abandoned", owner_clan_id=archived.id)
    target.defending_clans.append(archived)
    db.commit()

    service = ClanWarService()
    war = service.create_war(db, _payload(target, fighters), leader)
    assert war.war_type == "neutral_capture"
    assert war.defending_clan_id is None
    assert war.required_wins > 0
    assert service.cancel_active_wars_with_deleted_clans(db) == 0
    db.expire_all()
    assert war.status == "active"
    assert target.owner_clan_id is None
    assert not target.defending_clans
    assert len(war.attack_point_spends) == 1
    assert service.get_war_readiness(db, clan.id, leader)["attack_points"]["available"] == 0


def test_readiness_returns_level_points_candidates_and_no_uuid(db):
    _rules(db)
    clan, leader, fighters = _clan(db, "ready")
    db.commit()

    readiness = ClanWarService().get_war_readiness(db, clan.id, leader)

    assert readiness["level"]["level"] == 1
    assert readiness["attack_points"]["available"] == 1
    assert readiness["minimum_squad_size"] == 1
    assert readiness["warlord_limit"] == 1
    assert readiness["warlord_count"] == 1
    assert next(
        candidate for candidate in readiness["candidates"]
        if candidate["user_id"] == fighters[0]
    )["is_warlord"] is True
    assert {candidate["user_id"] for candidate in readiness["candidates"]} >= set(fighters)
    assert all("external_uuid" not in candidate for candidate in readiness["candidates"])


def test_occupied_attack_creates_synthetic_whole_clan_defense(db):
    _rules(db)
    attacker, leader, fighters = _clan(db, "attacker")
    defender, _, _ = _clan(db, "defender")
    target = _territory(db, "occupied", owner_clan_id=defender.id, status="active")
    db.commit()

    war = ClanWarService().create_war(db, _payload(target, fighters), leader)

    groups = {deployment.clan_id: deployment for deployment in war.deployments}
    assert groups[attacker.id].eligibility_scope == "squad"
    assert groups[defender.id].eligibility_scope == "whole_clan"
    assert groups[defender.id].members == []


@pytest.mark.parametrize(
    ("original_land_count", "expected_scope"),
    [(0, "whole_clan"), (1, "squad")],
)
def test_neutral_challenge_preserves_first_claim_defense_rule(
    db, original_land_count, expected_scope
):
    _rules(db)
    first_clan, first_leader, first_fighters = _clan(db, "first")
    second_clan, second_leader, second_fighters = _clan(db, "second")
    target = _territory(db, "challenge")
    source = None
    if original_land_count:
        source = _territory(
            db,
            "source",
            owner_clan_id=first_clan.id,
            status="active",
            adjacent_territory_ids=[target.id],
        )
        target.adjacent_territory_ids = [source.id]
    db.commit()
    service = ClanWarService()
    first_war = service.create_war(
        db,
        _payload(target, first_fighters, source=source),
        first_leader,
    )
    original_snapshot = dict(first_war.rules_snapshot)

    challenged = service.create_war(
        db,
        _payload(target, second_fighters),
        second_leader,
    )

    assert challenged.id == first_war.id
    assert challenged.attacking_clan_id == second_clan.id
    assert challenged.defending_clan_id == first_clan.id
    groups = {deployment.clan_id: deployment for deployment in challenged.deployments}
    assert groups[first_clan.id].current_role == "defender"
    assert groups[first_clan.id].eligibility_scope == expected_scope
    assert groups[second_clan.id].current_role == "attacker"
    assert groups[second_clan.id].eligibility_scope == "squad"
    assert challenged.rules_snapshot == original_snapshot
    assert len(challenged.attack_point_spends) == 2


def test_level_one_can_attack_with_only_its_warlord(db):
    _rules(db)
    _, leader, fighters = _clan(db, "level-one")
    target = _territory(db, "level-one")
    db.commit()

    war = ClanWarService().create_war(db, _payload(target, fighters[:1]), leader)

    assert [member.user_id for member in war.deployments[0].members] == fighters[:1]


def test_active_warlord_cannot_be_removed_or_replaced(db):
    _rules(db)
    clan, leader, fighters = _clan(db, "locked-warlord")
    target = _territory(db, "locked-warlord")
    db.commit()
    ClanWarService().create_war(db, _payload(target, fighters[:1]), leader)

    with pytest.raises(HTTPException) as error:
        ClanService().set_member_warlord(
            db,
            clan.id,
            fighters[0],
            False,
            leader,
        )

    assert error.value.status_code == 403


def test_level_two_requires_five_members_in_attack_squad(db):
    _rules(db)
    clan, leader, fighters = _clan(db, "invalid", member_count=11)
    source = _territory(db, "owned-one", owner_clan_id=clan.id, status="active")
    _territory(db, "owned-two", owner_clan_id=clan.id, status="active")
    target = _territory(db, "rollback")
    source.adjacent_territory_ids = [target.id]
    target.adjacent_territory_ids = [source.id]
    db.commit()

    with pytest.raises(HTTPException) as error:
        ClanWarService().create_war(db, _payload(target, fighters[:4]), leader)

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "squad_too_small"
    assert db.query(ClanWar).count() == 0
    assert db.query(WarDeployment).count() == 0
    assert db.query(ClanAttackPointSpend).count() == 0


def test_attack_requires_selected_warlord_to_be_in_squad(db):
    _rules(db)
    _, leader, fighters = _clan(db, "missing-warlord")
    target = _territory(db, "missing-warlord")
    db.commit()
    payload = ClanWarCreate(
        territory_id=target.id,
        squad_member_ids=fighters[1:2],
        warlord_user_id=fighters[0],
        expected_rule_version=1,
    )

    with pytest.raises(HTTPException) as error:
        ClanWarService().create_war(db, payload, leader)

    assert error.value.detail["code"] == "warlord_not_in_squad"


def test_attack_rejects_member_without_warlord_status(db):
    _rules(db)
    _, leader, fighters = _clan(db, "not-warlord")
    target = _territory(db, "not-warlord")
    db.commit()
    payload = ClanWarCreate(
        territory_id=target.id,
        squad_member_ids=fighters[1:2],
        warlord_user_id=fighters[1],
        expected_rule_version=1,
    )

    with pytest.raises(HTTPException) as error:
        ClanWarService().create_war(db, payload, leader)

    assert error.value.detail["code"] == "warlord_not_assigned"


def test_stale_rule_version_rolls_back_without_spending(db):
    _rules(db)
    _, leader, fighters = _clan(db, "stale")
    target = _territory(db, "stale")
    db.commit()

    with pytest.raises(HTTPException) as error:
        ClanWarService().create_war(
            db,
            _payload(target, fighters, version=999),
            leader,
        )

    assert error.value.status_code == 409
    assert error.value.detail["code"] == "campaign_rules_changed"
    assert db.query(ClanAttackPointSpend).count() == 0


def test_legacy_neutral_claim_cannot_be_challenged(db):
    _rules(db)
    old_clan, _, _ = _clan(db, "old")
    _, challenger, fighters = _clan(db, "challenger")
    target = _territory(db, "legacy")
    legacy = ClanWar(
        territory_id=target.id,
        attacking_clan_id=old_clan.id,
        war_type="neutral_capture",
        status="active",
        scoring_version="elo_team_v2",
        ends_at=NOW + timedelta(days=4),
    )
    db.add(legacy)
    db.commit()

    with pytest.raises(HTTPException) as error:
        ClanWarService().create_war(db, _payload(target, fighters), challenger)

    assert error.value.status_code == 409
    assert error.value.detail["code"] == "legacy_war_not_challengeable"
    assert db.query(WarDeployment).count() == 0


def test_cancel_refunds_v3_spend_and_releases_attack_members(db):
    _rules(db)
    _, leader, fighters = _clan(db, "cancel")
    target = _territory(db, "cancel")
    db.commit()
    service = ClanWarService()
    war = service.create_war(db, _payload(target, fighters), leader)
    spend = war.attack_point_spends[0]

    service.cancel_war(db, war.id, refund_attack=True)

    assert spend.refunded_at is not None
    assert all(member.released_at is not None for member in war.deployments[0].members)
    assert db.query(WarDeploymentMember).filter_by(released_at=None).count() == 0


def test_normal_completion_releases_members_without_refunding_spend(db):
    _rules(db)
    clan, leader, fighters = _clan(db, "complete")
    target = _territory(db, "complete")
    db.commit()
    service = ClanWarService()
    war = service.create_war(db, _payload(target, fighters), leader)
    spend = war.attack_point_spends[0]

    service._complete_war(db, war, clan.id)

    assert spend.refunded_at is None
    assert all(member.released_at is not None for member in war.deployments[0].members)


def test_season_reset_cancels_war_refunds_future_spend_and_releases_squad(db):
    _rules(db)
    _, leader, fighters = _clan(db, "season")
    target = _territory(db, "season")
    db.commit()
    war = ClanWarService().create_war(db, _payload(target, fighters), leader)
    spend = war.attack_point_spends[0]

    ClanEconomyService().start_new_season(
        db,
        100,
        actor_user_id=leader.id,
        season_name="Reset test",
    )

    db.refresh(war)
    db.refresh(spend)
    assert war.status == "canceled"
    assert spend.refunded_at is not None
    assert all(member.released_at is not None for member in war.deployments[0].members)
