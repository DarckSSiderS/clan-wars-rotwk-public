from datetime import datetime

from app.models.achievement import Achievement, UserAchievement
from app.models.match import Match
from app.models.user import User
from app.services.account_onboarding_service import AccountOnboardingService
from app.services.achievement_service import UserAchievementService
from app.services.external_identity_service import ExternalIdentityService
from app.services.user_service import UserService


def placeholder(db, name):
    user = User(username=name, is_claimed=False, is_active=True, hashed_password="!")
    db.add(user)
    db.commit()
    return user


def game(db, name, index):
    db.add(Match(match_id=f"rename-{index}", winner_player=name,
                 loser_player="Opponent", winner_faction="Men", loser_faction="Elves",
                 match_date=datetime(2026, 9, 1)))
    db.commit()


def test_oauth_absorbs_unclaimed_current_name_and_preserves_rewards(db):
    old = placeholder(db, "NewName")
    old_id = old.id
    achievement = Achievement(name="First", description="First game", icon="first",
                              category="combat", requirement_type="matches",
                              requirement_value=1, target_value=1, reward_amount=7)
    db.add(achievement)
    db.flush()
    db.add(UserAchievement(user_id=old.id, achievement_id=achievement.id,
                           progress=1, is_completed=True))
    old.balance = 7
    db.commit()
    game(db, "NewName", 1)

    user, _ = AccountOnboardingService().get_or_create_arena_user(db, "arena-uuid", "NewName")
    user.history_mode = "full"
    db.commit()
    assert user.username == "NewName"
    assert db.get(User, old_id) is None
    assert db.query(User).count() == 1
    assert db.query(UserAchievement).one().user_id == user.id
    UserAchievementService().sync_user_achievements(db, user.id)
    assert user.balance == 7


def test_old_names_are_canonicalized_in_matches_and_repeat_imports(db):
    from app.models.match import MatchParticipant
    user, _ = AccountOnboardingService().get_or_create_arena_user(db, "arena-uuid", "OldName")
    game(db, "OldName", 1)
    match = db.query(Match).one()
    db.add(MatchParticipant(match_id=match.id, nickname="OldName", is_winner=True, team=1))
    db.commit()
    AccountOnboardingService().get_or_create_arena_user(db, "arena-uuid", "NewName")
    assert db.query(Match).one().winner_player == "NewName"
    assert db.query(MatchParticipant).one().nickname == "NewName"
    game(db, "OldName", 2)
    assert UserService().ensure_ladder_profile(db, "OldName").id == user.id
    assert {match.winner_player for match in db.query(Match)} == {"NewName"}


def test_no_uuid_import_reuses_old_alias_after_oauth_rename(db):
    user, _ = AccountOnboardingService().get_or_create_arena_user(db, "arena-uuid", "OldName")
    game(db, "OldName", 1)
    renamed, created = AccountOnboardingService().get_or_create_arena_user(db, "arena-uuid", "NewName")
    assert not created
    assert renamed.id == user.id
    assert renamed.username == "NewName"
    assert UserService().ensure_ladder_profile(db, "oldname").id == user.id
    assert db.query(User).count() == 1


def test_importing_old_uuid_match_does_not_revert_verified_current_name(db):
    user, _ = AccountOnboardingService().get_or_create_arena_user(db, "arena-uuid", "NewName")
    UserService().ensure_ladder_profile(db, "OldName", "arena-uuid")
    db.refresh(user)
    assert user.external_identities[0].current_nickname == "NewName"
    assert user.display_name == "NewName"
    assert "OldName" in ExternalIdentityService().names_for_user(db, user.id)


def test_achievements_and_basic_stats_include_aliases(db):
    user, _ = AccountOnboardingService().get_or_create_arena_user(db, "arena-uuid", "OldName")
    game(db, "OldName", 1)
    AccountOnboardingService().get_or_create_arena_user(db, "arena-uuid", "NewName")
    game(db, "NewName", 2)
    user.history_mode = "full"
    db.add(Achievement(name="Two", description="Two games", icon="two", category="combat",
                       requirement_type="matches", requirement_value=2, target_value=2, reward_amount=10))
    db.commit()
    UserAchievementService().sync_user_achievements(db, user.id)
    UserAchievementService().sync_user_achievements(db, user.id)
    assert db.query(UserAchievement).one().is_completed
    assert user.balance == 10
    assert UserService().get_user_statistics(db, "NewName")["total_matches"] == 2


def test_claimed_namesake_is_never_merged(db):
    other = placeholder(db, "NewName")
    other.is_claimed = True
    db.commit()
    user, _ = AccountOnboardingService().get_or_create_arena_user(db, "arena-uuid", "NewName")
    assert other.id != user.id
    assert db.get(User, other.id).is_claimed


def test_placeholder_with_other_uuid_is_never_merged(db):
    other = placeholder(db, "NewName")
    ExternalIdentityService().observe(db, other, "other-uuid", "NewName")
    user, _ = AccountOnboardingService().get_or_create_arena_user(db, "arena-uuid", "NewName")
    assert other.id != user.id
    assert db.get(User, other.id) is not None


def test_new_history_achievements_exclude_older_alias_matches(db):
    user, _ = AccountOnboardingService().get_or_create_arena_user(db, "arena-uuid", "OldName")
    game(db, "OldName", 1)
    user.history_mode = "new"
    user.statistics_started_at = datetime(2026, 9, 10)
    db.add(Achievement(name="First", description="First game", icon="first", category="combat",
                       requirement_type="matches", requirement_value=1, target_value=1))
    db.commit()
    UserAchievementService().sync_user_achievements(db, user.id)
    assert db.query(UserAchievement).one().progress == 0
