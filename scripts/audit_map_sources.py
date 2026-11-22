"""Показывает, какие источники превью доступны у последних карт."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal
from app.models.match import Match
from app.services.map_preview_storage_service import MapPreviewStorageService


def main():
    with SessionLocal() as db:
        storage = MapPreviewStorageService()
        known_sources = {
            map_id: source
            for map_id, source in db.query(Match.map_id, Match.map_preview_source)
            .filter(
                Match.map_id.isnot(None),
                Match.map_preview_source.isnot(None),
            )
            .all()
        }
        rows = (
            db.query(Match)
            .filter(Match.map_name.isnot(None))
            .order_by(Match.match_date.desc())
            .all()
        )
        unique_maps = {}
        for match in rows:
            mode = match.gamemode_name or match.game_mode or ""
            if str(mode).strip().startswith("1"):
                continue
            key = (match.map_name or "").casefold()
            if key not in unique_maps:
                payload = match.source_payload or {}
                public_payload = payload.get("PublicApiPayload") or {}
                unique_maps[key] = {
                    "map_name": match.map_name,
                    "map_id": match.map_id,
                    "map_preview_source": match.map_preview_source,
                    "game_mode": mode,
                    "known_source_by_map_id": known_sources.get(match.map_id),
                    "local_preview_url": storage.public_url(match.map_name),
                    "payload_keys": sorted(public_payload.keys()),
                }
        print(json.dumps(list(unique_maps.values()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
