from datetime import datetime

from app.models.achievement import Achievement
from app.models.match import Match, MatchParticipant
from app.models.user import User
from app.services.achievement_service import UserAchievementService
from app.services.bootstrap_service import ensure_progression_content


def _match(match_id, mode, winner, loser, faction="Мордор"):
    match = Match(
        match_id=match_id,
        winner_player=winner,
        winner_faction=faction,
        loser_player=loser,
        loser_faction="Гондор",
        match_date=datetime(2026, 8, 1, 12, 0),
        duration="00:12:00",
        game_mode=mode,
        gamemode_name=mode,
        map_name="Fords of Isen",
    )
    match.participants = [
        MatchParticipant(nickname=winner, faction=faction, team=1, is_winner=True),
        MatchParticipant(nickname=loser, faction="Гондор", team=2, is_winner=False),
    ]
    return match


def test_available_achievements_use_supported_replay_requirements(db):
    ensure_progression_content(db)

    achievements = db.query(Achievement).filter(Achievement.is_available == True).all()

    assert achievements
    assert all(
        UserAchievementService.supports_requirement(item.requirement_type)
        for item in achievements
    )
    assert len([item for item in achievements if item.achievement_type == "career_matches"]) == 4
    assert len([item for item in achievements if item.achievement_type == "team_games"]) == 4
    assert len([item for item in achievements if item.achievement_type == "faction_wins:Мордор"]) == 4
    assert len([item for item in achievements if item.achievement_type == "map_wins:Fords of Isen"]) == 4


def test_progress_normalizes_modes_and_counts_faction_wins(db):
    ensure_progression_content(db)
    user = User(
        username="TestHero",
        email="testhero@example.com",
        hashed_password="test",
        balance=0,
    )
    db.add(user)
    db.add_all([
        _match("achievement-1v1", "1 vs 1", "TestHero", "EnemyOne"),
        _match("achievement-2v2", "2 versus 2", "TestHero", "EnemyTwo"),
    ])
    db.commit()

    achievements = UserAchievementService().get_user_achievements(db, user.id)
    by_name = {item.achievement.name: item for item in achievements}

    assert by_name["team_games_bronze"].progress == 1
    assert by_name["mode_1v1_games_bronze"].progress == 1
    assert by_name["mode_2v2_games_bronze"].progress == 1
    faction_wins = [
        item for item in achievements
        if item.achievement.achievement_type == "faction_wins:Мордор"
    ]
    assert {item.progress for item in faction_wins} == {2}
