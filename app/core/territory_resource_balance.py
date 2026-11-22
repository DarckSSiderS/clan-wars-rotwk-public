from __future__ import annotations

from dataclasses import dataclass

from app.core.section_55_balance import (
    ORDINARY_TIER_BALANCE,
    STRONGHOLD_TIER_BALANCE,
)


RESOURCE_TYPES = frozenset({"iron", "wood", "food", "mithril"})


@dataclass(frozen=True)
class TerritoryBalance:
    resource_type: str
    resource_output: int
    secondary_resource_type: str | None
    resource_wealth: int
    influence_value: int
    required_influence: int
    required_territories: int
    stronghold_power: int


def _ordinary(
    resource_type: str,
    tier: str = "standard",
    *,
    output: int = 1,
) -> TerritoryBalance:
    wealth, influence, required_influence = ORDINARY_TIER_BALANCE[tier]
    return TerritoryBalance(
        resource_type=resource_type,
        resource_output=output,
        secondary_resource_type=None,
        resource_wealth=wealth,
        influence_value=influence,
        required_influence=required_influence,
        required_territories=0,
        stronghold_power=0,
    )


def _stronghold(
    resource_type: str,
    secondary_resource_type: str,
    tier: str,
) -> TerritoryBalance:
    wealth, influence, required_influence, required_territories, power = (
        STRONGHOLD_TIER_BALANCE[tier]
    )
    return TerritoryBalance(
        resource_type=resource_type,
        resource_output=1,
        secondary_resource_type=secondary_resource_type,
        resource_wealth=wealth,
        influence_value=influence,
        required_influence=required_influence,
        required_territories=required_territories,
        stronghold_power=power,
    )


# Resource means the territory's strategic specialization in the campaign, not
# that no other material exists there. When Tolkien did not identify a literal
# deposit, terrain, settlement type, trade, and neighbouring access determine
# the specialization. Mithril is deliberately restricted to the Moria lode.
TERRITORY_BALANCE: dict[str, TerritoryBalance] = {
    "Эвендим": _ordinary("food"),
    "Рун": _ordinary("food", "valuable"),
    "Арнор": _ordinary("food"),
    "Форност": _ordinary("iron", "valuable"),
    "Троллистое плато": _ordinary("wood", "frontier"),
    "Долина Митлонд": _ordinary("wood", "hub", output=2),
    "Форлиндон": _ordinary("wood", "valuable"),
    "Харлиндон": _ordinary("wood", "valuable"),
    "Шир": _ordinary("food", "hub", output=2),
    "Башенные холмы (Эмин Берайд)": _ordinary("iron"),
    "Ривенделл (Имладрис)": _stronghold("wood", "food", "minor"),
    "Эрегион (Холлин)": _ordinary("iron", "valuable", output=2),
    "Высокий Перевал": _ordinary("iron", "frontier"),
    "Врата Мории": _ordinary("mithril", "valuable", output=2),
    "Перевал Карадрас": _ordinary("mithril", "frontier"),
    "Долина Азанулбизар (Димрил-Дейл)": _ordinary("iron", output=2),
    "Чернолесье (Темнолесье)": _ordinary("wood", "hub", output=2),
    "Дол Гулдур": _stronghold("wood", "iron", "minor"),
    "Дейл": _ordinary("food", "hub", output=2),
    "Подземелья Эребора": _stronghold("iron", "food", "major"),
    "Железные холмы": _ordinary("iron", "hub", output=2),
    "Степи Рованиона": _ordinary("food", "valuable"),
    "Келдуин": _ordinary("food", "valuable"),
    "Эред Митрин (Серые горы)": _ordinary("iron", output=2),
    "Гора Гундабад": _ordinary("iron", "valuable", output=2),
    "Каррок": _ordinary("food"),
    "Восточный Эмнет": _ordinary("food", "valuable"),
    "Волд": _ordinary("food"),
    "Хельмова Падь (Западная Марка)": _stronghold("iron", "food", "major"),
    "Фангорн": _ordinary("wood", "hub", output=2),
    "Дунланд": _ordinary("food"),
    "Изенские броды": _ordinary("food"),
    "Река Адорн": _ordinary("food"),
    "Изенгард": _stronghold("iron", "wood", "minor"),
    "Осгилиат": _ordinary("iron", "valuable"),
    "Минас Тирит": _stronghold("iron", "food", "capital"),
    "Пеленнорские поля": _ordinary("food", "hub", output=2),
    "Центральный Итилиен": _ordinary("food", "valuable"),
    "Итилиенские холмы": _ordinary("wood", "valuable", output=2),
    "Ламедон и Рингло": _ordinary("food", "valuable"),
    "Белфалас": _ordinary("food", "hub"),
    "Анфалас": _ordinary("food"),
    "Андраст": _ordinary("wood", "frontier"),
    "Умбар": _stronghold("wood", "iron", "minor"),
    "Чёрные Врата (Мораннон)": _ordinary("iron", "valuable"),
    "Дагорлад": _ordinary("iron", "frontier"),
    "Мёртвые Топи": _ordinary("iron", "frontier"),
    "Удун": _stronghold("iron", "wood", "capital"),
    "Роковая Гора (Ородруин)": _ordinary("iron", "hub", output=2),
    "Минас Моргул": _stronghold("iron", "food", "major"),
    "Мордорские пустоши": _ordinary("iron", "frontier"),
    "Море Нурнен": _ordinary("food", "hub", output=2),
    "Северный Рун": _ordinary("food", "valuable"),
    "Дальний Харад": _ordinary("food"),
    "Харад (Оазис)": _ordinary("food", "hub"),
    "Энедвайт": _ordinary("wood", output=2),
    "Ближние земли Кханда": _ordinary("iron", output=2),
    "Бурые равнины": _ordinary("food", "frontier"),
    "Заверть": _ordinary("iron"),
    "Западная марка (Шир)": _ordinary("food", "hub", output=2),
    "Кардолан": _ordinary("food"),
    "Карн Дум": _stronghold("iron", "food", "major"),
    "Курганы (Тирн-Гортхад)": _ordinary("iron", "frontier"),
    "Лес Друадан": _ordinary("wood", "valuable", output=2),
    "Лес Зелёной Листвы": _ordinary("wood", "hub", output=2),
    "Лострианд": _ordinary("wood", "valuable"),
    "Минхириат": _ordinary("wood"),
    "Рудаур": _ordinary("iron"),
    "Форохел": _ordinary("food", "frontier"),
    "Фородвейд": _ordinary("food", "frontier"),
    "Северные холмы": _ordinary("food"),
    "Бри": _ordinary("food", "valuable"),
    "Лебеннин": _ordinary("food", "hub", output=2),
    "Восточный Рохан": _ordinary("food", "valuable"),
    "Эмин Муил": _ordinary("iron", "frontier"),
}
