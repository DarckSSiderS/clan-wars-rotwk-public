import argparse
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.clan_colors import CLAN_MAP_COLORS
from app.database import SessionLocal
from app.models.clan import Clan


def assign_test_clan_colors(db, clans, colors) -> None:
    if len(clans) != len(colors):
        raise ValueError("Количество кланов и цветов должно совпадать")

    for clan in clans:
        clan.map_color = None
    db.flush()

    for clan, color in zip(clans, colors):
        clan.map_color = color
        clan.map_color_change_used = False
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Назначает обычным тестовым кланам уникальные случайные цвета.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Подтверждает изменение данных кланов.",
    )
    args = parser.parse_args()
    if not args.confirm:
        parser.error("для изменения данных передайте --confirm")

    with SessionLocal() as db:
        clans = (
            db.query(Clan)
            .filter(Clan.is_admin_clan.is_(False))
            .order_by(Clan.id)
            .all()
        )
        if len(clans) > len(CLAN_MAP_COLORS):
            raise RuntimeError("В палитре недостаточно уникальных цветов для всех кланов")

        colors = random.SystemRandom().sample(sorted(CLAN_MAP_COLORS), len(clans))
        assign_test_clan_colors(db, clans, colors)

        for clan in clans:
            print(f"{clan.id}: {clan.name} = {clan.map_color}")


if __name__ == "__main__":
    main()
