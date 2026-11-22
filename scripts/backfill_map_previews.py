import argparse
import asyncio
import sys
from pathlib import Path

import aiohttp

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal
from app.models.match import Match
from app.services.map_preview_storage_service import MapPreviewStorageService


async def backfill(limit: int | None = None) -> tuple[int, int]:
    db = SessionLocal()
    storage = MapPreviewStorageService()
    saved = 0
    skipped = 0
    try:
        rows = (
            db.query(Match.map_name, Match.map_id, Match.map_preview_source)
            .filter(
                Match.map_name.isnot(None),
            )
            .distinct()
            .order_by(Match.map_name.asc())
            .all()
        )
        unique_maps = {}
        for map_name, map_id, source_url in rows:
            normalized = storage._normalized_name(map_name)
            if normalized and normalized not in unique_maps:
                unique_maps[normalized] = (map_name, map_id, source_url)

        timeout = aiohttp.ClientTimeout(total=45, connect=15)
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
        ) as session:
            for index, (map_name, map_id, source_url) in enumerate(unique_maps.values()):
                if limit is not None and index >= limit:
                    break
                if not source_url:
                    source_url = storage._preview_catalog().get(map_id or "", {}).get("source")
                if await storage.download(map_name, source_url, session):
                    saved += 1
                else:
                    skipped += 1
                await asyncio.sleep(0.1)
        return saved, skipped
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Сохраняет локальные превью всех известных карт BFME Ladder.",
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    saved, skipped = asyncio.run(backfill(args.limit))
    print(f"Превью готовы: {saved}; не удалось сохранить: {skipped}")


if __name__ == "__main__":
    main()
