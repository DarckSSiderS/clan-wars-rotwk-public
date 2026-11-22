"""Initial military development for the campaign map (requirements 80-81)."""

from app.core.territory_resource_balance import TERRITORY_BALANCE


# Campaign design tiers: rural/wilderness lands start at 1, settled lands at 2,
# military centres and defensible passes at 3, all great strongholds at 4.
SETTLED_TERRITORIES = frozenset({
    "Арнор", "Рун", "Долина Митлонд", "Форлиндон", "Харлиндон",
    "Эрегион (Холлин)", "Чернолесье (Темнолесье)", "Дейл", "Каррок",
    "Келдуин", "Дунланд", "Центральный Итилиен", "Итилиенские холмы",
    "Ламедон и Рингло", "Белфалас", "Северный Рун", "Харад (Оазис)",
    "Энедвайт", "Ближние земли Кханда", "Кардолан", "Лес Друадан",
    "Лес Зелёной Листвы", "Лострианд", "Рудаур", "Бри", "Лебеннин",
    "Восточный Рохан",
})
MILITARY_TERRITORIES = frozenset({
    "Форност", "Башенные холмы (Эмин Берайд)", "Высокий Перевал",
    "Врата Мории", "Перевал Карадрас", "Долина Азанулбизар (Димрил-Дейл)",
    "Железные холмы", "Эред Митрин (Серые горы)", "Гора Гундабад",
    "Изенские броды", "Осгилиат", "Чёрные Врата (Мораннон)",
})


def initial_military_level(
    name: str, *, is_playable: bool = True, stronghold_power: int = 0,
) -> int:
    if not is_playable or name.casefold() in {"тол-фалас", "tol-falas", "tol falas"}:
        return 0
    balance = TERRITORY_BALANCE.get(name)
    if stronghold_power > 0 or (balance and balance.stronghold_power > 0):
        return 4
    if name in MILITARY_TERRITORIES:
        return 3
    if name in SETTLED_TERRITORIES:
        return 2
    return 1
