from app.api.v1.quests import _quest_text


def test_quest_keys_have_human_readable_russian_fallbacks():
    title = _quest_text(None, "quest_daily_first_win", "ru")
    description = _quest_text(None, "quest_daily_first_win_desc", "ru")
    unknown = _quest_text(None, "quest_missing_translation", "ru")

    assert title == "Первая победа дня"
    assert description == "Победите в одном матче за день"
    assert unknown == "Задание"
    assert not title.startswith("quest_")
    assert not description.startswith("quest_")
