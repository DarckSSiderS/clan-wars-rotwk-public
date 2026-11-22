from datetime import timedelta

from app.core.campaign_rules import default_campaign_rule_values
from app.models.campaign import CampaignRuleSet
from app.models.clan import Clan, ClanMember, ClanMembershipPeriod
from app.models.clan_asset import ClanAsset, ClanOwnedAsset
from app.models.external_identity import ExternalPlayerIdentity
from app.models.match import Match, MatchParticipant
from app.models.territory import Territory
from app.models.user import User
from app.schemas.war import ClanWarCreate
from app.services.war_service import ClanWarService


def _rules(db):
    row = CampaignRuleSet(
        version=1,
        values=default_campaign_rule_values(),
        is_active=True,
        reason="test",
    )
    db.add(row)
    db.flush()


def _clan(db, suffix, *, count=6):
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
        member = ClanMember(
            user_id=user.id,
            clan_id=clan.id,
            is_warlord=index == 0,
        )
        period = ClanMembershipPeriod(
            user_id=user.id,
            clan_id=clan.id,
            started_at=user.created_at,
            started_reason="test",
        )
        identity = ExternalPlayerIdentity(
            user_id=user.id,
            external_uuid=f"uuid-{suffix}-{index}",
            current_nickname=user.username,
            verification_status="verified",
        )
        db.add_all([member, period, identity])
        fighters.append(user)
    db.flush()
    return clan, leader, fighters


def _active_v3_war(db):
    _rules(db)
    attacker, leader, attackers = _clan(db, "attacker")
    defender, _, defenders = _clan(db, "defender")
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


def _match(db, war, winners, losers, suffix):
    played_at = war.started_at + timedelta(minutes=5)
    size = max(len(winners), len(losers))
    mode = f"{size} versus {size}"
    match = Match(
        match_id=f"deployment-{suffix}",
        winner_player=winners[0].username,
        winner_player_uuid=f"uuid-{winners[0].username}",
        winner_faction="Gondor",
        loser_player=losers[0].username,
        loser_player_uuid=f"uuid-{losers[0].username}",
        loser_faction="Mordor",
        match_date=played_at,
        duration="00:05:00",
        game_mode=mode,
        gamemode_name=mode,
        patch_name="Patch 2.02 (9.6.5)",
        patch_id="official-2:9.6.5",
        rating_patch_family="patch_202",
        is_valid=True,
        elo_delta=10,
    )
    db.add(match)
    db.flush()
    for is_winner, team in ((True, winners), (False, losers)):
        for user in team:
            identity = user.external_identities[0]
            db.add(
                MatchParticipant(
                    match_id=match.id,
                    nickname=user.username,
                    player_uuid=identity.external_uuid,
                    team=1 if is_winner else 2,
                    is_winner=is_winner,
                    old_rank=100,
                    new_rank=99 if is_winner else 101,
                    elo=1000,
                )
            )
    db.commit()
    ClanWarService().record_match_result(
        db,
        winners[0].username,
        losers[0].username,
        match_date=played_at,
        match=match,
    )
    return war.match_results[-1]


def test_one_assigned_attacker_in_2v2_gets_half_share_and_scaled_relic(db):
    war, attacker, attackers, _, defenders = _active_v3_war(db)
    outsider = User(
        username="winner-outsider",
        email="winner-outsider@example.test",
        hashed_password="x",
    )
    db.add(outsider)
    db.flush()
    db.add(
        ExternalPlayerIdentity(
            user_id=outsider.id,
            external_uuid="uuid-outsider",
            current_nickname=outsider.username,
            verification_status="verified",
        )
    )
    relic = ClanAsset(
        key="scoring-relic",
        name="Scoring relic",
        bonus_type="war_win_points",
        bonus_value=4,
    )
    db.add(relic)
    db.flush()
    db.add(
        ClanOwnedAsset(
            clan_id=attacker.id,
            asset_id=relic.id,
            purchased_by=war.attacking_clan.leader_id,
            level=1,
            is_active=True,
        )
    )
    war.rules_snapshot = {
        **war.rules_snapshot,
        "RELIC_BONUSES_BY_CLAN": {str(attacker.id): {"war_win_points": 4}},
    }
    db.commit()

    result = _match(
        db,
        war,
        [attackers[0], outsider],
        defenders[:2],
        "half",
    )

    assert result.winner_participation_share == 0.5
    assert result.winner_clan_members == 1
    assert result.winner_relic_bonus_points == 2
    assert result.winner_eligibility_code == "attack_squad_member"


def test_two_assigned_attackers_in_2v2_get_full_share_and_team_bonus(db):
    war, _, attackers, _, defenders = _active_v3_war(db)

    result = _match(db, war, attackers[:2], defenders[:2], "full")

    assert result.winner_participation_share == 1.0
    assert result.winner_team_bonus_percent == 10
    assert result.winner_clan_members == 2


def test_unassigned_attacker_scores_zero_while_eligible_defender_still_counts(db):
    war, _, attackers, _, defenders = _active_v3_war(db)

    result = _match(db, war, [attackers[5]], [defenders[0]], "unassigned")

    assert result.is_counted is True
    assert result.winner_total_points == 0
    assert result.winner_participation_share == 0
    assert result.winner_eligibility_code == "not_assigned_to_attack_squad"
    assert result.loser_eligibility_code == "defending_clan_member"


def test_v3_recalculation_keeps_scoring_version_and_deployment_scope(db):
    war, _, attackers, _, defenders = _active_v3_war(db)
    result = _match(db, war, [attackers[5]], [defenders[0]], "recalc")

    ClanWarService().recalculate_active_war(db, war.id)
    db.refresh(result)

    assert war.scoring_version == "elo_team_v3_squads"
    assert result.scoring_version == "elo_team_v3_squads"
    assert result.winner_total_points == 0
    assert result.winner_eligibility_code == "not_assigned_to_attack_squad"


def test_squad_defender_uses_original_snapshot_not_the_whole_clan(db):
    _rules(db)
    first_clan, first_leader, first_fighters = _clan(db, "first")
    _, second_leader, second_fighters = _clan(db, "second")
    target = Territory(
        name="Neutral target",
        region="Test",
        svg_path_data="M10 0",
        required_influence=30,
    )
    db.add(target)
    db.flush()
    source = Territory(
        name="First source",
        region="Test",
        svg_path_data="M11 0",
        owner_clan_id=first_clan.id,
        status="active",
        adjacent_territory_ids=[target.id],
    )
    db.add(source)
    db.flush()
    target.adjacent_territory_ids = [source.id]
    db.commit()
    service = ClanWarService()
    war = service.create_war(
        db,
        ClanWarCreate(
            territory_id=target.id,
            source_territory_id=source.id,
            squad_member_ids=[user.id for user in first_fighters[:5]],
            warlord_user_id=first_fighters[0].id,
            expected_rule_version=1,
        ),
        first_leader,
    )
    war = service.create_war(
        db,
        ClanWarCreate(
            territory_id=target.id,
            squad_member_ids=[user.id for user in second_fighters[:5]],
            warlord_user_id=second_fighters[0].id,
            expected_rule_version=1,
        ),
        second_leader,
    )

    result = _match(
        db,
        war,
        [first_fighters[5]],
        [second_fighters[0]],
        "squad-defender",
    )

    assert result.winner_clan_id == first_clan.id
    assert result.winner_participation_share == 0
    assert result.winner_total_points == 0
    assert result.winner_eligibility_code == "not_assigned_to_attack_squad"
