import hashlib
import json
import logging
import re
from pathlib import Path
from urllib.parse import urljoin

from app.config import settings


logger = logging.getLogger(__name__)


class MapPreviewStorageService:
    _catalog_cache: dict[str, dict[str, str]] | None = None

    def __init__(self, storage_dir: str | Path | None = None):
        self.storage_dir = Path(storage_dir or settings.MAP_PREVIEW_STORAGE_DIR)

    @classmethod
    def _preview_catalog(cls) -> dict[str, dict[str, str]]:
        if cls._catalog_cache is not None:
            return cls._catalog_cache
        catalog_path = Path(__file__).resolve().parents[1] / "data" / "map_preview_sources.json"
        try:
            cls._catalog_cache = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cls._catalog_cache = {}
        return cls._catalog_cache

    @classmethod
    def source_for_match(cls, match) -> str | None:
        if match.map_preview_source:
            return match.map_preview_source
        entry = cls._preview_catalog().get(str(match.map_id or ""), {})
        return entry.get("source")

    @staticmethod
    def _normalized_name(map_name: str | None) -> str:
        return " ".join(str(map_name or "").strip().casefold().split())

    def map_key(self, map_name: str | None) -> str | None:
        normalized = self._normalized_name(map_name)
        if not normalized:
            return None
        slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:48]
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        return f"{slug or 'map'}-{digest}"

    def target_path(self, map_name: str | None) -> Path | None:
        key = self.map_key(map_name)
        return self.storage_dir / key if key else None

    def public_url(self, map_name: str | None) -> str | None:
        target = self.target_path(map_name)
        if target and target.is_file():
            return f"/api/v1/statistics/map-previews/{target.name}"
        return None

    def resolve_key(self, map_key: str) -> Path | None:
        if not re.fullmatch(r"[a-z0-9-]{20,80}", map_key):
            return None
        target = (self.storage_dir / map_key).resolve()
        storage_root = self.storage_dir.resolve()
        try:
            target.relative_to(storage_root)
        except ValueError:
            return None
        return target if target.is_file() else None

    @staticmethod
    def media_type(data: bytes) -> str | None:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        return None

    async def download(
        self,
        map_name: str | None,
        source_url: str | None,
        session,
    ) -> bool:
        target = self.target_path(map_name)
        if target is None or not source_url:
            return False
        if target.is_file() and target.stat().st_size > 0:
            return True

        url = urljoin(settings.LADDER_API_BASE, source_url)
        temporary = target.with_name(f"{target.name}.part")
        target.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        first_bytes = bytearray()
        try:
            async with session.get(url, allow_redirects=True) as response:
                if response.status != 200:
                    raise RuntimeError(f"BFME Ladder вернул HTTP {response.status}")
                with temporary.open("wb") as image_file:
                    async for chunk in response.content.iter_chunked(32 * 1024):
                        if not chunk:
                            continue
                        size += len(chunk)
                        if size > settings.MAP_PREVIEW_MAX_FILE_SIZE:
                            raise RuntimeError("Изображение карты превышает разрешённый размер")
                        if len(first_bytes) < 16:
                            first_bytes.extend(chunk[:16 - len(first_bytes)])
                        image_file.write(chunk)

            if size == 0:
                raise RuntimeError("BFME Ladder вернул пустое изображение")
            if self.media_type(bytes(first_bytes)) is None:
                raise RuntimeError("Источник вернул файл неподдерживаемого формата")
            temporary.replace(target)
            return True
        except Exception as exc:
            if temporary.exists():
                temporary.unlink()
            logger.warning(
                "Не удалось сохранить превью карты %s: %s",
                map_name or "без названия",
                exc,
            )
            return False

    async def download_match(self, match, session) -> bool:
        return await self.download(
            match.map_name,
            self.source_for_match(match),
            session,
        )
