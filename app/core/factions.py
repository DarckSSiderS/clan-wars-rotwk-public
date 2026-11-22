from collections.abc import Iterable


FACTIONS_BY_PATCH: dict[str, tuple[str, ...]] = {
    "ennorath": (
        "Гондор",
        "Арнор",
        "Рохан",
        "Лотлориэн",
        "Имладрис",
        "Гномы",
        "Изенгард",
        "Мордор",
        "Мглистые Горы",
        "Ангмар",
        "Харад",
        "Рун",
    ),
    "patch_202": (
        "Люди",
        "Эльфы",
        "Гномы",
        "Изенгард",
        "Мордор",
        "Гоблины",
        "Ангмар",
    ),
}


_FACTION_ALIASES = {
    "gondor": "Гондор",
    "rohan": "Рохан",
    "isengard": "Изенгард",
    "mordor": "Мордор",
    "angmar": "Ангмар",
    "dwarves": "Гномы",
    "dwarf": "Гномы",
    "elves": "Эльфы",
    "elf": "Эльфы",
    "goblins": "Гоблины",
    "goblin": "Гоблины",
    "men": "Люди",
    "harad": "Харад",
    "arnor": "Арнор",
    "lothlorien": "Лотлориэн",
    "lothlórien": "Лотлориэн",
    "imladris": "Имладрис",
    "misty mountains": "Мглистые Горы",
    "rhun": "Рун",
    "rhûn": "Рун",
}
_FACTION_ALIASES.update(
    {
        faction.casefold(): faction
        for factions in FACTIONS_BY_PATCH.values()
        for faction in factions
    }
)


def normalize_faction(value: str | None) -> str | None:
    if not value:
        return None
    return _FACTION_ALIASES.get(str(value).strip().casefold())


def build_patch_faction_statistics(
    rows: Iterable[tuple[str | None, str | None, int]],
) -> dict[str, list[dict[str, int | str]]]:
    counts = {
        patch: {faction: 0 for faction in factions}
        for patch, factions in FACTIONS_BY_PATCH.items()
    }
    for patch_family, raw_faction, raw_count in rows:
        if patch_family not in counts:
            continue
        faction = normalize_faction(raw_faction)
        if faction not in counts[patch_family]:
            continue
        counts[patch_family][faction] += int(raw_count or 0)

    result: dict[str, list[dict[str, int | str]]] = {}
    for patch, factions in FACTIONS_BY_PATCH.items():
        order = {faction: index for index, faction in enumerate(factions)}
        sorted_factions = sorted(
            factions,
            key=lambda faction: (-counts[patch][faction], order[faction]),
        )
        result[patch] = [
            {"faction": faction, "count": counts[patch][faction]}
            for faction in sorted_factions
        ]
    return result
