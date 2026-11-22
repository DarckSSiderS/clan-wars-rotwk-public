"""Stable keys are independent of the Russian display names."""

ROLES = {
    "staff": "Хранитель",
    "ennorath": "Ennorath",
    "patch202": "Patch 2.02",
    "news": "Вести Средиземья",
    "beacons": "Маяки Гондора",
}

# key, display name, [(key, display name, kind, access)]
LAYOUT = [
    (
        "entrance",
        "✦ Врата Средиземья",
        [
            ("welcome", "приветствие", "text", "read"),
            ("rules", "правила", "text", "read"),
            ("roles", "роли-и-привязка", "text", "read"),
        ],
    ),
    (
        "news",
        "✦ Вести",
        [
            ("news", "новости", "text", "read"),
            ("updates", "обновления", "text", "read"),
        ],
    ),
    (
        "campaign",
        "✦ Клановые войны",
        [
            ("campaign", "сводка-кампании", "text", "read"),
            ("chronicle", "хроника-войн", "text", "read"),
            ("recruitment", "набор-в-кланы", "text", "read"),
            ("hall", "зал-славы", "text", "read"),
        ],
    ),
    (
        "community",
        "✦ Сообщество",
        [
            (key, name, "text", "threads" if key == "ideas" else "public")
            for key, name in [
                ("chat", "общение"),
                ("replays", "реплеи"),
                ("tactics", "тактики"),
                ("ideas", "предложения"),
                ("bugs", "ошибки"),
            ]
        ],
    ),
    (
        "voice",
        "✦ Голосовые",
        [
            ("voice", "Общий зал", "voice", "public"),
            ("voice-create", "➕ Создать отряд", "voice", "public"),
        ],
    ),
    (
        "staff",
        "✦ Совет хранителей",
        [
            ("moderation", "журнал-модерации", "text", "staff"),
            ("status", "состояние-палантира", "text", "staff"),
        ],
    ),
]
