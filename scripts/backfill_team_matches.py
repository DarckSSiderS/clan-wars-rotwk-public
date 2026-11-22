"""Догружает несколько реальных командных матчей без сдвига рабочего курсора."""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal
from app.services.ladder_service import ladder_service


TEAM_MODES = {"2 versus 2", "3 versus 3", "4 versus 4"}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--per-mode", type=int, default=3)
    return parser.parse_args()


async def run(days: int, per_mode: int):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=max(1, days))
    with SessionLocal() as db:
        imported = await ladder_service.fetch_and_save_matches_from_api(
            db,
            new_limit=max(1, per_mode * len(TEAM_MODES)),
            gamemodes=TEAM_MODES,
            start_override_ms=int(start.timestamp() * 1000),
            end_override_ms=int(end.timestamp() * 1000),
            advance_cursor=False,
            max_per_mode=max(1, per_mode),
        )
    print(f"Импортировано новых командных матчей: {imported}")


if __name__ == "__main__":
    arguments = parse_args()
    asyncio.run(run(arguments.days, arguments.per_mode))
