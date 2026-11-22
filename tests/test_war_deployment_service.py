from datetime import datetime, timedelta, timezone

import pytest

from app.core.campaign_rules import default_campaign_rule_values
from app.models.campaign import CampaignRuleSet
from app.models.clan import Clan, ClanMember, ClanMembershipPeriod
from app.models.external_identity import ExternalPlayerIdentity
from app.models.territory import Territory
from app.models.user import User
from app.models.war import ClanWar
from app.services.campaign_rule_service import CampaignRuleService
from app.services.war_deployment_service import (
    DeploymentConflict,
    SquadValidationError,
    WarDeploymentService,
)


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def _context(db, *, count=6):
    leader = User(username="leader", email="leader@example.test", hashed_password="x")
    db.add(leader)
    db.flush()
    clan = Clan(name="Attackers", leader_id=leader.id)
    db.add(clan)
    db.flush()
    fighters = []
    for index in range(count):
        user = User(
            username=f"fighter-{index}",
            email=f"fighter-{index}@example.test",
            hashed_password="x",
        )
        db.add(user)
        db.flush()
        member = ClanMember(
            user_id=user.id,
            clan_id=clan.id,
            joined_at=NOW - timedelta(days=30),
            is_warlord=index == 0,
        )
        identity = ExternalPlayerIdentity(
            user_id=user.id,
            external_uuid=f"uuid-{index}",
            current_nickname=f"Nick {index}",
            verification_status="verified",
        )
        period = ClanMembershipPeriod(
            user_id=user.id,
            clan_id=clan.id,
            started_at=NOW - timedelta(days=30),
            started_reason="test",
        )
        db.add_all([member, identity, period])
        fighters.append((user, member, identity, period))
    territory = Territory(name="Target", region="Test", svg_path_data="M0 0")
    rule_row = CampaignRuleSet(
        version=1,
        values=default_campaign_rule_values(),
        is_active=True,
        reason="test",
    )
    db.add_all([territory, rule_row])
    db.flush()
    return (
        leader,
        clan,
        fighters,
        territory,
        CampaignRuleService().get_active(db),
    )


def _war(db, clan, territory, *, suffix="one", defender_id=None):
    war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=clan.id,
        defending_clan_id=defender_id,
        war_type="neutral_capture" if defender_id is None else "territory_attack",
        status="active",
        started_at=NOW,
        ends_at=NOW + timedelta(hours=96),
        scoring_version="elo_team_v3_squads",
    )
    db.add(war)
    db.flush()
    return war


def test_candidates_show_verification_activity_and_attack_lock(db):
    leader, clan, fighters, territory, rule_set = _context(db)
    service = WarDeploymentService()
    members = service.validate_squad(
        db,
        clan.id,
        [row[0].id for row in fighters[:5]],
        minimum_size=5,
        warlord_user_id=fighters[0][0].id,
    )
    deployment = service.create_attack(
        db,
        _war(db, clan, territory),
        clan,
        members,
        source_territory_id=None,
        territory_count=0,
        actor_user_id=leader.id,
        rule_set=rule_set,
        claim_sequence=1,
        warlord_user_id=fighters[0][0].id,
    )
    fighters[-1][2].verification_status = "unverified"

    candidates = service.candidates(
        db,
        clan.id,
        activity={fighter[0].id: index for index, fighter in enumerate(fighters)},
    )

    by_id = {candidate.user_id: candidate for candidate in candidates}
    assert by_id[fighters[0][0].id].busy_war_id == deployment.war_id
    assert by_id[fighters[0][0].id].is_warlord is True
    assert by_id[fighters[0][0].id].busy_in_attack is True
    assert by_id[fighters[-1][0].id].verified is False
    assert by_id[fighters[-1][0].id].activity_matches == 5


def test_validate_squad_requires_minimum_unique_current_verified_members(db):
    _, clan, fighters, _, _ = _context(db)
    service = WarDeploymentService()
    ids = [row[0].id for row in fighters]

    with pytest.raises(SquadValidationError, match="squad_too_small"):
        service.validate_squad(db, clan.id, ids[:4], minimum_size=5, warlord_user_id=ids[0])
    with pytest.raises(SquadValidationError, match="squad_duplicate_members"):
        service.validate_squad(db, clan.id, [*ids[:4], ids[0]], minimum_size=5, warlord_user_id=ids[0])

    fighters[4][2].verification_status = "unverified"
    with pytest.raises(SquadValidationError, match="squad_member_unverified"):
        service.validate_squad(db, clan.id, ids[:5], minimum_size=5, warlord_user_id=ids[0])

    fighters[4][2].verification_status = "verified"
    db.delete(fighters[4][1])
    db.flush()
    with pytest.raises(SquadValidationError, match="squad_member_not_in_clan"):
        service.validate_squad(db, clan.id, ids[:5], minimum_size=5, warlord_user_id=ids[0])


def test_activity_is_not_required_for_squad_assignment(db):
    _, clan, fighters, _, _ = _context(db)

    result = WarDeploymentService().validate_squad(
        db,
        clan.id,
        [row[0].id for row in fighters[:5]],
        minimum_size=5,
        warlord_user_id=fighters[0][0].id,
    )

    assert len(result) == 5


def test_attack_snapshot_is_immutable_and_blocks_second_active_attack(db):
    leader, clan, fighters, territory, rule_set = _context(db)
    service = WarDeploymentService()
    ids = [row[0].id for row in fighters[:5]]
    members = service.validate_squad(
        db, clan.id, ids, minimum_size=5, warlord_user_id=ids[0]
    )
    deployment = service.create_attack(
        db,
        _war(db, clan, territory),
        clan,
        members,
        source_territory_id=territory.id,
        territory_count=1,
        actor_user_id=leader.id,
        rule_set=rule_set,
        claim_sequence=1,
        warlord_user_id=ids[0],
    )
    original_nickname = deployment.members[0].nickname_snapshot
    original_uuid = deployment.members[0].external_uuid_snapshot
    fighters[0][2].current_nickname = "Renamed"
    fighters[0][2].external_uuid = "changed-uuid"

    assert deployment.members[0].nickname_snapshot == original_nickname
    assert deployment.members[0].external_uuid_snapshot == original_uuid
    with pytest.raises(DeploymentConflict) as error:
        service.validate_squad(
            db, clan.id, ids, minimum_size=5, warlord_user_id=ids[0]
        )
    assert set(error.value.user_ids) == set(ids)


@pytest.mark.parametrize(
    ("territory_count", "expected_scope", "expected_rule"),
    [
        (0, "whole_clan", "whole_clan_if_challenged"),
        (1, "squad", "squad_if_challenged"),
    ],
)
def test_neutral_claim_defense_rule_is_fixed_at_assignment(
    db, territory_count, expected_scope, expected_rule
):
    leader, clan, fighters, territory, rule_set = _context(db)
    service = WarDeploymentService()
    deployment = service.create_attack(
        db,
        _war(db, clan, territory),
        clan,
        service.validate_squad(
            db,
            clan.id,
            [row[0].id for row in fighters[:5]],
            minimum_size=5,
            warlord_user_id=fighters[0][0].id,
        ),
        source_territory_id=None,
        territory_count=territory_count,
        actor_user_id=leader.id,
        rule_set=rule_set,
        claim_sequence=1,
        warlord_user_id=fighters[0][0].id,
    )
    clan.owned_territories.clear()

    transitioned = service.transition_neutral_claim_to_defense(
        db, deployment, now=NOW + timedelta(hours=1)
    )

    assert transitioned.current_role == "defender"
    assert transitioned.eligibility_scope == expected_scope
    assert transitioned.defense_rule == expected_rule
    assert all(member.released_at is not None for member in transitioned.members)


def test_released_defenders_can_join_another_attack(db):
    leader, clan, fighters, territory, rule_set = _context(db)
    service = WarDeploymentService()
    ids = [row[0].id for row in fighters[:5]]
    deployment = service.create_attack(
        db,
        _war(db, clan, territory),
        clan,
        service.validate_squad(
            db, clan.id, ids, minimum_size=5, warlord_user_id=ids[0]
        ),
        source_territory_id=None,
        territory_count=1,
        actor_user_id=leader.id,
        rule_set=rule_set,
        claim_sequence=1,
        warlord_user_id=ids[0],
    )
    service.transition_neutral_claim_to_defense(
        db, deployment, now=NOW + timedelta(hours=1)
    )

    second_members = service.validate_squad(
        db, clan.id, ids, minimum_size=5, warlord_user_id=ids[0]
    )

    assert len(second_members) == 5


def test_whole_clan_defense_uses_verified_membership_at_match_time(db):
    _, clan, fighters, territory, rule_set = _context(db)
    service = WarDeploymentService()
    opponent_leader = User(
        username="opponent", email="opponent@example.test", hashed_password="x"
    )
    db.add(opponent_leader)
    db.flush()
    opponent = Clan(name="Opponent", leader_id=opponent_leader.id)
    db.add(opponent)
    db.flush()
    war = _war(db, opponent, territory, defender_id=clan.id)
    deployment = service.create_whole_clan_defense(
        db,
        war,
        clan.id,
        defense_rule="occupied_territory_owner",
        rule_set=rule_set,
        now=NOW,
    )
    fighters[0][3].ended_at = NOW - timedelta(minutes=1)
    fighters[1][2].verification_status = "unverified"

    side = service.eligible_side(db, war, clan.id, NOW)

    assert deployment.members == []
    assert side.scope == "whole_clan"
    assert {user.id for user in side.users} == {row[0].id for row in fighters[2:]}
    assert side.eligibility_code == "defending_clan_member"
