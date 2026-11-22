from app.core.economy_balance import GREAT_CITY_BALANCE, is_admin_territory_name


CANONICAL_GREAT_CITIES = {
    "Ривенделл (Имладрис)",
    "Подземелья Эребора",
    "Дол Гулдур",
    "Изенгард",
    "Минас Тирит",
    "Удун",
    "Минас Моргул",
    "Карн Дум",
    "Умбар",
    "Хельмова Падь (Западная Марка)",
}


def test_balance_contains_every_canonical_great_city():
    missing = {
        name
        for name in CANONICAL_GREAT_CITIES
        if name.casefold() not in GREAT_CITY_BALANCE
    }

    assert missing == set()


def test_admin_island_is_recognized_but_not_a_great_city():
    assert is_admin_territory_name("Тол-Фалас") is True
    assert "тол-фалас" not in GREAT_CITY_BALANCE
