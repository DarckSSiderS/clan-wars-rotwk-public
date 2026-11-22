from datetime import datetime, timedelta, timezone

from app.models.clan import Clan, ClanMember, ClanMembershipPeriod
from app.models.external_identity import ExternalPlayerIdentity
from app.models.match import Match, MatchParticipant
from app.models.territory import Territory
from app.models.user import User
from app.models.war import ClanWar, ClanWarMatchResult, ClanWarParticipant
from app.services.clan_membership_service import ClanMembershipService
from app.services.war_service import ClanWarService


def add_user(db, user_id: int, username: str) -> User:
    user = User(
        id=user_id,
        username=username,
        email=f"{username}@example.com",
        hashed_password="unused",
        is_claimed=True,
    )
    db.add(user)
    db.flush()
    db.add(
        ExternalPlayerIdentity(
            user_id=user.id,
            external_uuid=f"uuid-{username}",
            current_nickname=username,
            verification_status="verified",
        )
    )
    return user


def add_ranked_match(
    db,
    match_id: str,
    winner: User,
    loser: User,
    played_at: datetime,
    *,
    duration: str = "00:10:00",
    elo_delta: int = 12,
    is_valid: bool = True,
    mode: str = "1 versus 1",
    patch_family: str = "patch_202",
) -> Match:
    match = Match(
        match_id=match_id,
        winner_player=winner.username,
        winner_faction="Люди",
        loser_player=loser.username,
        loser_faction="Мордор",
        match_date=played_at,
        duration=duration,
        game_mode=mode,
        gamemode_name=mode,
        elo_delta=elo_delta,
        is_valid=is_valid,
        map_name="Форност",
        patch_version="2.02 v9",
        rating_patch_family=patch_family,
    )
    db.add(match)
    db.flush()
    return match


def test_clan_preferred_patch_is_informational_for_war_scoring(db):
    played_at = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)
    warrior = add_user(db, 1, "cross-patch-warrior")
    outsider = add_user(db, 2, "cross-patch-outsider")
    defender = add_user(db, 3, "cross-patch-defender")
    attacking_clan = Clan(
        id=92,
        name="Ennorath regulars",
        leader_id=warrior.id,
        preferred_patch="ennorath",
    )
    defending_clan = Clan(
        id=93,
        name="Patch defenders",
        leader_id=defender.id,
        preferred_patch="patch_202",
    )
    db.add_all([attacking_clan, defending_clan])
    db.flush()
    db.add(ClanMembershipPeriod(
        user_id=warrior.id,
        clan_id=attacking_clan.id,
        started_at=played_at - timedelta(days=1),
    ))
    territory = Territory(
        id=92,
        name="Cross patch territory",
        region="test",
        svg_path_data="M 0 0",
        owner_clan_id=defending_clan.id,
    )
    db.add(territory)
    db.flush()
    war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=attacking_clan.id,
        defending_clan_id=defending_clan.id,
        war_type="territory_attack",
        status="active",
        started_at=played_at - timedelta(hours=1),
        ends_at=played_at + timedelta(days=4),
        attacker_patch="ennorath",
        defender_patch="patch_202",
    )
    match = add_ranked_match(
        db,
        "cross-patch-ranked",
        warrior,
        outsider,
        played_at,
        patch_family="patch_202",
    )
    db.add(war)
    db.commit()

    ClanWarService().record_match_result(
        db,
        warrior.username,
        outsider.username,
        played_at,
        match=match,
    )

    result = db.query(ClanWarMatchResult).filter_by(war_id=war.id).one()
    assert result.is_counted is True
    assert result.rejection_reason is None
    assert result.patch_family == "patch_202"


def test_full_clan_team_gets_controlled_team_bonus(db):
    played_at = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    attackers = [add_user(db, index, f"attacker-{index}") for index in range(1, 4)]
    defenders = [add_user(db, index, f"defender-{index}") for index in range(4, 7)]
    attacking_clan = Clan(id=90, name="Team attackers", leader_id=attackers[0].id)
    defending_clan = Clan(id=91, name="Team defenders", leader_id=defenders[0].id)
    db.add_all([attacking_clan, defending_clan])
    db.flush()
    for user in attackers:
        db.add(ClanMembershipPeriod(
            user_id=user.id,
            clan_id=attacking_clan.id,
            started_at=played_at - timedelta(days=1),
        ))
    for user in defenders:
        db.add(ClanMembershipPeriod(
            user_id=user.id,
            clan_id=defending_clan.id,
            started_at=played_at - timedelta(days=1),
        ))
    territory = Territory(
        id=90,
        name="Team territory",
        region="test",
        svg_path_data="M 0 0",
        owner_clan_id=defending_clan.id,
    )
    db.add(territory)
    db.flush()
    war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=attacking_clan.id,
        defending_clan_id=defending_clan.id,
        war_type="territory_attack",
        status="active",
        started_at=played_at - timedelta(hours=1),
        ends_at=played_at + timedelta(days=4),
        attacker_power=0,
        defender_power=0,
    )
    match = add_ranked_match(
        db,
        "ranked-team-3v3",
        attackers[0],
        defenders[0],
        played_at,
        mode="3 versus 3",
    )
    for team, users, is_winner in (
        (1, attackers, True),
        (2, defenders, False),
    ):
        for user in users:
            db.add(MatchParticipant(
                match_id=match.id,
                nickname=user.username,
                player_uuid=f"uuid-{user.username}",
                faction="Люди" if is_winner else "Мордор",
                team=team,
                is_winner=is_winner,
                elo=1000,
            ))
    db.add(war)
    db.commit()

    ClanWarService().record_match_result(
        db,
        match.winner_player,
        match.loser_player,
        match.match_date,
        match=match,
    )

    result = db.query(ClanWarMatchResult).filter_by(war_id=war.id).one()
    assert result.is_counted is True
    assert result.game_mode == "3 versus 3"
    assert result.winner_team_size == 3
    assert result.winner_clan_members == 3
    assert result.winner_base_points == 12
    assert result.winner_team_bonus_percent == 10
    assert result.winner_team_bonus_points == 1.2
    assert result.winner_total_points == 13.2
    scores = db.query(ClanWarParticipant).filter_by(war_id=war.id).all()
    attacker_scores = [row for row in scores if row.clan_id == attacking_clan.id]
    assert len(attacker_scores) == 3
    assert all(row.wins == 1 and row.war_points == 4.4 for row in attacker_scores)


def test_membership_period_opens_and_closes_with_exact_times(db):
    user = add_user(db, 1, "member")
    clan = Clan(id=10, name="Clan", leader_id=user.id)
    db.add(clan)
    db.flush()
    joined_at = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    left_at = joined_at + timedelta(days=3)
    member = ClanMember(
        user_id=user.id,
        clan_id=clan.id,
        joined_at=joined_at,
    )
    db.add(member)
    db.commit()

    service = ClanMembershipService()
    period = service.start(db, member, reason="test_join")
    service.end(db, member, reason="test_leave", ended_at=left_at)

    assert period.started_reason == "test_join"
    assert period.ended_reason == "test_leave"
    assert service.clan_ids_at(db, user.id, joined_at) == {clan.id}
    assert service.clan_ids_at(db, user.id, left_at) == set()
    assert service.clan_ids_at(db, user.id, left_at + timedelta(seconds=1)) == set()


def test_delayed_match_uses_clans_from_match_time(db):
    played_at = datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc)
    switched_at = played_at + timedelta(days=1)
    winner = add_user(db, 1, "winner")
    loser = add_user(db, 2, "loser")
    old_clan = Clan(
        id=10,
        name="Old clan",
        leader_id=winner.id,
        map_color="#2E8B57",
        map_emblem_url="/images/clans/map-emblems/old.webp",
    )
    defending_clan = Clan(
        id=11,
        name="Defending clan",
        leader_id=loser.id,
        map_color="#1E6FB9",
        map_emblem_url="/images/clans/map-emblems/defender.webp",
    )
    current_clan = Clan(id=12, name="Current clan", leader_id=winner.id)
    db.add_all([old_clan, defending_clan, current_clan])
    db.flush()
    db.add_all(
        [
            ClanMember(
                user_id=winner.id,
                clan_id=current_clan.id,
                joined_at=switched_at,
            ),
            ClanMember(
                user_id=loser.id,
                clan_id=defending_clan.id,
                joined_at=played_at - timedelta(days=1),
            ),
            ClanMembershipPeriod(
                user_id=winner.id,
                clan_id=old_clan.id,
                started_at=played_at - timedelta(days=2),
                ended_at=switched_at,
                started_reason="joined",
                ended_reason="switched_clan",
            ),
            ClanMembershipPeriod(
                user_id=winner.id,
                clan_id=current_clan.id,
                started_at=switched_at,
                started_reason="joined",
            ),
            ClanMembershipPeriod(
                user_id=loser.id,
                clan_id=defending_clan.id,
                started_at=played_at - timedelta(days=2),
                started_reason="joined",
            ),
        ]
    )
    territory = Territory(
        id=50,
        name="Test territory",
        region="test",
        svg_path_data="M 0 0",
        owner_clan_id=defending_clan.id,
    )
    db.add(territory)
    db.flush()
    source_match = Match(
        match_id="delayed-replay-1",
        winner_player=winner.username,
        winner_faction="Люди",
        loser_player=loser.username,
        loser_faction="Мордор",
        match_date=played_at,
        map_name="Форност",
        patch_version="2.02 v9",
        duration="00:10:00",
        game_mode="1 versus 1",
        gamemode_name="1 versus 1",
        elo_delta=12,
        is_valid=True,
    )
    db.add(source_match)
    db.flush()
    war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=old_clan.id,
        defending_clan_id=defending_clan.id,
        war_type="territory_attack",
        status="active",
        started_at=played_at - timedelta(hours=1),
        ends_at=played_at + timedelta(days=4),
        attacker_power=20,
        defender_power=0,
    )
    db.add(war)
    db.commit()

    service = ClanWarService()
    service.record_match_result(
        db,
        winner_player=winner.username,
        loser_player=loser.username,
        match_date=played_at,
        match=source_match,
    )
    service.record_match_result(
        db,
        winner_player=winner.username,
        loser_player=loser.username,
        match_date=played_at,
        match=source_match,
    )

    winner_score = db.query(ClanWarParticipant).filter_by(
        war_id=war.id,
        user_id=winner.id,
    ).one()
    loser_score = db.query(ClanWarParticipant).filter_by(
        war_id=war.id,
        user_id=loser.id,
    ).one()
    assert winner_score.clan_id == old_clan.id
    assert winner_score.wins == 1
    assert winner_score.war_points == 12
    assert loser_score.clan_id == defending_clan.id
    assert loser_score.losses == 1
    assert loser_score.war_points == 0
    result = db.query(ClanWarMatchResult).one()
    assert result.match_id == source_match.id
    assert result.winner_base_points == 10
    assert result.winner_power_percent == 20
    assert result.winner_power_bonus_points == 2
    assert result.winner_total_points == 12
    assert result.loser_total_points == 0
    serialized = service.serialize_war(db, war)
    assert serialized["tracked_matches"] == 1
    assert serialized["match_breakdown"][0]["match_id"] == "delayed-replay-1"
    assert serialized["clan_scores"][0]["power_bonus_points"] == 2
    assert serialized["attacking_clan_map_color"] == "#2E8B57"
    assert serialized["defending_clan_map_color"] == "#1E6FB9"
    assert serialized["attacking_clan_map_emblem_url"] == "/images/clans/map-emblems/old.webp"
    assert serialized["defending_clan_map_emblem_url"] == "/images/clans/map-emblems/defender.webp"

    service.record_match_result(
        db,
        winner_player=winner.username,
        loser_player=loser.username,
        match_date=switched_at + timedelta(hours=1),
    )
    assert winner_score.wins == 1
    assert loser_score.losses == 1


def test_match_before_membership_or_outside_war_is_ignored(db):
    match_time = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    winner = add_user(db, 1, "late_winner")
    loser = add_user(db, 2, "early_loser")
    clan_a = Clan(id=20, name="A", leader_id=winner.id)
    clan_b = Clan(id=21, name="B", leader_id=loser.id)
    db.add_all([clan_a, clan_b])
    db.flush()
    db.add_all(
        [
            ClanMembershipPeriod(
                user_id=winner.id,
                clan_id=clan_a.id,
                started_at=match_time + timedelta(hours=1),
            ),
            ClanMembershipPeriod(
                user_id=loser.id,
                clan_id=clan_b.id,
                started_at=match_time - timedelta(days=2),
            ),
        ]
    )
    territory = Territory(
        id=60,
        name="Other territory",
        region="test",
        svg_path_data="M 0 0",
    )
    db.add(territory)
    db.flush()
    db.add(
        ClanWar(
            territory_id=territory.id,
            attacking_clan_id=clan_a.id,
            defending_clan_id=clan_b.id,
            war_type="territory_attack",
            status="active",
            started_at=match_time - timedelta(hours=2),
            ends_at=match_time + timedelta(days=4),
        )
    )
    db.commit()

    ClanWarService().record_match_result(
        db,
        winner_player=winner.username,
        loser_player=loser.username,
        match_date=match_time,
    )

    assert db.query(ClanWarParticipant).count() == 0


def test_ranked_match_against_outsider_counts_at_two_minutes_or_more(db):
    played_at = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    warrior = add_user(db, 1, "warrior")
    outsider = add_user(db, 2, "outsider")
    defender = add_user(db, 3, "defender")
    attacking_clan = Clan(id=30, name="Attackers", leader_id=warrior.id)
    defending_clan = Clan(id=31, name="Defenders", leader_id=defender.id)
    db.add_all([attacking_clan, defending_clan])
    db.flush()
    db.add(
        ClanMembershipPeriod(
            user_id=warrior.id,
            clan_id=attacking_clan.id,
            started_at=played_at - timedelta(days=1),
        )
    )
    territory = Territory(
        id=70,
        name="Ranked territory",
        region="test",
        svg_path_data="M 0 0",
        owner_clan_id=defending_clan.id,
    )
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
    match = add_ranked_match(
        db,
        "ranked-outsider",
        warrior,
        outsider,
        played_at,
    )
    db.add(war)
    db.commit()

    service = ClanWarService()
    service.record_match_result(
        db,
        warrior.username,
        outsider.username,
        played_at,
        match=match,
    )

    participant = db.query(ClanWarParticipant).one()
    result = db.query(ClanWarMatchResult).one()
    assert participant.clan_id == attacking_clan.id
    assert participant.wins == 1
    assert participant.war_points == 10
    assert result.is_counted is True
    assert result.winner_clan_id == attacking_clan.id
    assert result.loser_clan_id is None
    assert service.serialize_war(db, war)["tracked_matches"] == 1

    participant.war_points = 99
    participant.wins = 9
    db.commit()
    first_recalculation = service.recalculate_active_war(db, war.id)
    second_recalculation = service.recalculate_active_war(db, war.id)
    db.refresh(participant)

    assert first_recalculation["counted"] == 1
    assert second_recalculation["counted"] == 1
    assert participant.wins == 1
    assert participant.war_points == 10


def test_short_unranked_and_clanmate_matches_are_explained(db):
    played_at = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)
    warrior = add_user(db, 1, "warrior")
    clanmate = add_user(db, 2, "clanmate")
    outsider = add_user(db, 3, "outsider")
    defender = add_user(db, 4, "defender")
    attacking_clan = Clan(id=40, name="Attackers", leader_id=warrior.id)
    defending_clan = Clan(id=41, name="Defenders", leader_id=defender.id)
    db.add_all([attacking_clan, defending_clan])
    db.flush()
    db.add_all(
        [
            ClanMembershipPeriod(
                user_id=warrior.id,
                clan_id=attacking_clan.id,
                started_at=played_at - timedelta(days=1),
            ),
            ClanMembershipPeriod(
                user_id=clanmate.id,
                clan_id=attacking_clan.id,
                started_at=played_at - timedelta(days=1),
            ),
        ]
    )
    territory = Territory(
        id=80,
        name="Review territory",
        region="test",
        svg_path_data="M 0 0",
        owner_clan_id=defending_clan.id,
    )
    db.add(territory)
    db.flush()
    war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=attacking_clan.id,
        defending_clan_id=defending_clan.id,
        war_type="territory_attack",
        status="active",
        started_at=played_at - timedelta(hours=1),
        ends_at=played_at + timedelta(days=4),
    )
    short_match = add_ranked_match(
        db,
        "short-ranked",
        warrior,
        outsider,
        played_at,
        duration="00:00:59",
    )
    unranked_match = add_ranked_match(
        db,
        "unranked",
        warrior,
        outsider,
        played_at + timedelta(minutes=1),
        elo_delta=0,
    )
    clanmate_match = add_ranked_match(
        db,
        "clanmates",
        warrior,
        clanmate,
        played_at + timedelta(minutes=2),
        duration="00:15:00",
    )
    db.add(war)
    db.commit()

    service = ClanWarService()
    for source_match in (short_match, unranked_match, clanmate_match):
        service.record_match_result(
            db,
            source_match.winner_player,
            source_match.loser_player,
            source_match.match_date,
            match=source_match,
        )

    results = {
        result.match.match_id: result
        for result in db.query(ClanWarMatchResult).all()
    }
    assert db.query(ClanWarParticipant).count() == 0
    assert results["short-ranked"].rejection_reason == "Матч короче 1 минуты"
    assert results["unranked"].rejection_reason == (
        "Матч не является валидным рейтинговым 1v1, 2v2, 3v3 или 4v4"
    )
    assert results["clanmates"].rejection_reason == "Матч сыгран между соклановцами"
    serialized = service.serialize_war(db, war)
    assert serialized["tracked_matches"] == 0
    assert serialized["rejected_matches"] == 3


def test_defender_wins_when_points_are_equal_to_hundredths(db):
    scores = [
        {
            "clan_id": 1,
            "points": 10.004,
            "wins": 4,
            "win_rate": 80,
            "active_participants": 5,
            "matches": 5,
        },
        {
            "clan_id": 2,
            "points": 10.001,
            "wins": 1,
            "win_rate": 20,
            "active_participants": 1,
            "matches": 5,
        },
    ]

    assert ClanWarService()._select_winner(scores, defending_clan_id=2) == 2
