from datetime import datetime, timedelta, timezone

from app.models.clan import Clan, ClanMember, ClanMembershipPeriod
from app.models.match import Match
from app.models.territory import Territory
from app.models.user import User
from app.models.war import ClanWar, ClanWarMatchResult
from app.services.clan_experience_service import ClanExperienceService


def add_match(
    db,
    match_id: str,
    winner: str,
    loser: str,
    played_at: datetime,
    *,
    duration: str = "00:15:00",
    elo_delta: int = 12,
) -> Match:
    match = Match(
        match_id=match_id,
        winner_player=winner,
        winner_faction="Люди",
        loser_player=loser,
        loser_faction="Мордор",
        match_date=played_at,
        duration=duration,
        game_mode="1 versus 1",
        gamemode_name="1 versus 1",
        elo_delta=elo_delta,
        is_valid=True,
    )
    db.add(match)
    db.flush()
    return match


def test_clan_experience_uses_membership_wars_and_activity_coefficients(db):
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    player = User(
        id=1,
        username="Player",
        email="player@example.com",
        hashed_password="unused",
    )
    opponent = User(
        id=2,
        username="OpponentA",
        email="opponent@example.com",
        hashed_password="unused",
    )
    clan = Clan(id=10, name="Clan", leader_id=player.id)
    enemy_clan = Clan(id=11, name="Enemy", leader_id=opponent.id)
    db.add_all([player, opponent, clan, enemy_clan])
    db.flush()
    joined_at = now - timedelta(days=60)
    db.add_all(
        [
            ClanMember(
                user_id=player.id,
                clan_id=clan.id,
                joined_at=joined_at,
            ),
            ClanMembershipPeriod(
                user_id=player.id,
                clan_id=clan.id,
                started_at=joined_at,
                started_reason="joined",
            ),
        ]
    )
    war_match = add_match(
        db,
        "war-win",
        player.username,
        opponent.username,
        now - timedelta(days=1),
    )
    add_match(
        db,
        "regular-loss",
        "OpponentB",
        player.username,
        now - timedelta(days=2),
    )
    add_match(
        db,
        "older-win",
        player.username,
        "OpponentA",
        now - timedelta(days=40),
    )
    add_match(
        db,
        "too-short",
        player.username,
        "OpponentC",
        now - timedelta(days=3),
        duration="00:00:59",
    )
    territory = Territory(
        id=50,
        name="Territory",
        region="test",
        svg_path_data="M 0 0",
        owner_clan_id=enemy_clan.id,
    )
    db.add(territory)
    db.flush()
    war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=clan.id,
        defending_clan_id=enemy_clan.id,
        war_type="territory_attack",
        status="active",
        started_at=now - timedelta(days=2),
        ends_at=now + timedelta(days=2),
    )
    db.add(war)
    db.flush()
    db.add(
        ClanWarMatchResult(
            war_id=war.id,
            match_id=war_match.id,
            played_at=war_match.match_date,
            winner_user_id=player.id,
            loser_user_id=opponent.id,
            winner_clan_id=clan.id,
            loser_clan_id=enemy_clan.id,
            winner_base_points=3,
            winner_power_percent=20,
            winner_power_bonus_points=0.6,
            winner_relic_bonus_points=0,
            winner_total_points=3.6,
            loser_base_points=1,
            loser_power_percent=0,
            loser_power_bonus_points=0,
            loser_relic_bonus_points=0,
            loser_total_points=1,
            is_counted=True,
        )
    )
    db.commit()

    result = ClanExperienceService().calculate(
        db,
        player,
        clan.id,
        now=now,
    )

    assert result["clan_matches"] == 3
    assert result["clan_wins"] == 2
    assert result["clan_war_matches"] == 1
    assert result["clan_war_points"] == 3.6
    assert result["active_days_30"] == 2
    assert result["membership_days"] == 60
    assert result["unique_opponents"] == 2
    assert result["base_experience"] == 96
    assert result["activity_coefficient"] == 1.083
    assert result["loyalty_coefficient"] == 1.083
    assert result["diversity_coefficient"] == 1.02
    assert result["clan_experience"] == 115


def test_clan_experience_is_zero_without_membership(db):
    player = User(
        id=1,
        username="Player",
        email="player@example.com",
        hashed_password="unused",
    )
    db.add(player)
    db.commit()

    result = ClanExperienceService().calculate(db, player, clan_id=999)

    assert result["clan_experience"] == 0
    assert result["clan_matches"] == 0
