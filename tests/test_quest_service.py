from datetime import datetime, timedelta

from app.models.match import Match
from app.models.quest import Quest, QuestCategory, QuestType, UserQuest
from app.models.user import User
from app.services.quest_service import QuestService


def _user(db, suffix: str) -> User:
    user = User(
        username=f"quest-{suffix}",
        email=f"quest-{suffix}@example.test",
        hashed_password="unused",
        balance=100,
        level=1,
        experience=0,
    )
    db.add(user)
    db.flush()
    return user


def _quest(db, suffix: str, *, target: int = 3) -> Quest:
    quest = Quest(
        title_key=f"quest_{suffix}_title",
        description_key=f"quest_{suffix}_description",
        quest_type=QuestType.DAILY,
        category=QuestCategory.WINS,
        target_value=target,
        reward_coins=50,
        reward_experience=1000,
        is_active=True,
    )
    db.add(quest)
    db.flush()
    return quest


def test_quest_reward_can_only_be_claimed_once_and_is_atomic(db):
    user = _user(db, "claim")
    quest = _quest(db, "claim", target=1)
    user_quest = UserQuest(
        user_id=user.id,
        quest_id=quest.id,
        current_progress=1,
        is_completed=True,
        is_claimed=False,
        completed_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    db.add(user_quest)
    db.commit()

    service = QuestService()
    first = service.claim_quest_reward(db, user.id, quest.id)
    second = service.claim_quest_reward(db, user.id, quest.id)

    db.refresh(user)
    db.refresh(user_quest)
    assert first is not None
    assert first["new_balance"] == 150
    assert first["level_info"]["total_experience"] == 1000
    assert second is None
    assert user.balance == 150
    assert user.experience == 1000
    assert user_quest.is_claimed is True


def test_partial_quest_progress_is_committed_before_completion(db):
    user = _user(db, "progress")
    quest = _quest(db, "progress", target=3)
    user_quest = UserQuest(
        user_id=user.id,
        quest_id=quest.id,
        current_progress=0,
        is_completed=False,
        is_claimed=False,
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    match = Match(
        match_id="quest-progress-match",
        winner_player=user.username,
        winner_faction="Gondor",
        loser_player="quest-opponent",
        loser_faction="Mordor",
        match_date=datetime.utcnow(),
    )
    db.add_all([user_quest, match])
    db.commit()

    completed = QuestService().update_quest_progress(db, user.id)
    db.rollback()
    db.expire_all()
    stored = db.query(UserQuest).filter(UserQuest.id == user_quest.id).one()

    assert completed == []
    assert stored.current_progress == 1
    assert stored.is_completed is False


def test_quest_progress_summary_uses_the_canonical_service_update(db):
    user = _user(db, "summary")
    quest = _quest(db, "summary", target=1)
    user_quest = UserQuest(
        user_id=user.id,
        quest_id=quest.id,
        current_progress=0,
        is_completed=False,
        is_claimed=False,
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    match = Match(
        match_id="quest-summary-match",
        winner_player=user.username,
        winner_faction="Gondor",
        loser_player="quest-summary-opponent",
        loser_faction="Mordor",
        match_date=datetime.utcnow(),
    )
    db.add_all([user_quest, match])
    db.commit()

    summary = QuestService().update_quest_progress_summary(db, user.id)

    assert summary == {
        "active_count": 1,
        "updated_count": 1,
        "completed_count": 1,
        "completed_quests": [
            {
                "quest_id": quest.id,
                "quest_title": quest.title_key,
                "category": QuestCategory.WINS.value,
                "target_value": 1,
                "current_progress": 1,
            }
        ],
        "stats": {"total_matches": 1, "wins": 1},
    }
