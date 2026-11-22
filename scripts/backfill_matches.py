"""Import the available BFME Arena replay backlog without moving the worker cursor."""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal
from app.services.ladder_service import BFMELadderService


SUPPORTED_MODES = {
    "1 versus 1",
    "2 versus 2",
    "3 versus 3",
    "4 versus 4",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Import the replay backlog available from BFME Arena.",
    )
    parser.add_argument("--days", type=int, default=3650)
    parser.add_argument("--per-mode", type=int, default=500)
    parser.add_argument(
        "--mode",
        action="append",
        choices=sorted(SUPPORTED_MODES),
        dest="modes",
        help="Repeat to select modes; all supported modes are used by default.",
    )
    parser.add_argument(
        "--player",
        default="",
        help="Optional BFME Arena nickname used to search older player replays.",
    )
    return parser.parse_args()


async def run(*, days: int, per_mode: int, modes: set[str], player: str) -> int:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=max(1, days))
    service = BFMELadderService()
    with SessionLocal() as db:
        imported = await service.fetch_and_save_matches_from_api(
            db,
            new_limit=max(1, per_mode * len(modes)),
            gamemodes=modes,
            start_override_ms=int(start.timestamp() * 1000),
            end_override_ms=int(end.timestamp() * 1000),
            advance_cursor=False,
            max_per_mode=max(1, per_mode),
            player_query=player or None,
        )
    print(
        "Replay backfill complete: "
        f"source={service.last_source}, scanned={service.last_scanned_count}, "
        f"imported={imported}"
    )
    if service.last_source == "bfme_arena_html":
        print(
            "The HTML source covers the replay window exposed by the public archive. "
            "A configured public API token is required for a guaranteed full date-range backfill."
        )
    return imported


if __name__ == "__main__":
    arguments = parse_args()
    asyncio.run(
        run(
            days=arguments.days,
            per_mode=arguments.per_mode,
            modes=set(arguments.modes or SUPPORTED_MODES),
            player=arguments.player.strip(),
        )
    )
