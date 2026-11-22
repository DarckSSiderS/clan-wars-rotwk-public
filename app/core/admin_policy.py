PRIMARY_ADMIN_USERNAME = "clanwar"
LEGACY_ADMIN_USERNAMES = frozenset({"ar-adunaim"})


def normalize_username(username: str | None) -> str:
    return (username or "").strip().casefold()


def is_primary_admin(username: str | None) -> bool:
    return normalize_username(username) == PRIMARY_ADMIN_USERNAME.casefold()


def is_legacy_admin(username: str | None) -> bool:
    return normalize_username(username) in LEGACY_ADMIN_USERNAMES
