from app.models.clan import Clan
from deploy.randomize_test_clan_colors import assign_test_clan_colors


def test_randomizer_can_swap_existing_unique_colors(db):
    first = Clan(name="Первый тестовый клан", leader_id=1, map_color="#D32F2F")
    second = Clan(name="Второй тестовый клан", leader_id=2, map_color="#3949AB")
    db.add_all([first, second])
    db.commit()

    assign_test_clan_colors(db, [first, second], ["#3949AB", "#D32F2F"])

    assert first.map_color == "#3949AB"
    assert second.map_color == "#D32F2F"
