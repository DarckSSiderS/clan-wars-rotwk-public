import hashlib
import logging
import re
from pathlib import Path
from urllib.parse import quote, urljoin

from sqlalchemy.orm import Session

from app.config import settings
from app.core.time import utc_now
from app.models.match import Match
from app.services.elo_service import PATCH_202, PATCH_ENNORATH, get_patch_family


logger = logging.getLogger(__name__)

SUPPORTED_REPLAY_PATCHES = {PATCH_202, PATCH_ENNORATH}


class ReplayStorageService:
    def __init__(self, storage_dir: str | Path | None = None):
        self.storage_dir = Path(storage_dir or settings.REPLAY_STORAGE_DIR)

    @staticmethod
    def patch_family(match: Match) -> str | None:
        return (
            match.rating_patch_family
            or get_patch_family(match.patch_name, match.patch_id)
            or get_patch_family(match.patch_version, match.patch_id)
        )

    def is_supported(self, match: Match) -> bool:
        return self.patch_family(match) in SUPPORTED_REPLAY_PATCHES

    @staticmethod
    def download_url(match: Match) -> str:
        if match.replay_download_url:
            return urljoin(settings.LADDER_API_BASE, match.replay_download_url)
        replay_id = quote(str(match.match_id), safe="")
        return f"{settings.LADDER_API_BASE}/download?replayId={replay_id}"

    def target_path(self, match: Match) -> Path:
        safe_id = re.sub(r"[^A-Za-z0-9._-]", "_", str(match.match_id))
        if not safe_id.lower().endswith(".bfme2replay"):
            safe_id = f"{safe_id}.BfME2Replay"
        return self.storage_dir / safe_id

    async def download_match(self, db: Session, match: Match, session) -> bool:
        if not self.is_supported(match):
            return False

        target = self.target_path(match)
        target.parent.mkdir(parents=True, exist_ok=True)
        if (
            match.replay_download_status == "downloaded"
            and target.is_file()
            and match.replay_file_size == target.stat().st_size
        ):
            return True

        url = self.download_url(match)
        temporary = target.with_suffix(f"{target.suffix}.part")
        digest = hashlib.sha256()
        size = 0
        try:
            headers = {}
            token = settings.LADDER_PUBLIC_API_TOKEN.strip()
            if token:
                headers["Authorization"] = f"Bearer {token}"
            async with session.get(
                url,
                allow_redirects=True,
                headers=headers,
            ) as response:
                if response.status != 200:
                    raise RuntimeError(f"BFME Ladder вернул HTTP {response.status}")
                with temporary.open("wb") as replay_file:
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        size += len(chunk)
                        if size > settings.REPLAY_MAX_FILE_SIZE:
                            raise RuntimeError("Файл превышает разрешенный размер")
                        digest.update(chunk)
                        replay_file.write(chunk)

            if size == 0:
                raise RuntimeError("BFME Ladder вернул пустой файл")
            temporary.replace(target)
            match.replay_download_url = url
            match.replay_local_path = str(target.resolve())
            match.replay_file_size = size
            match.replay_sha256 = digest.hexdigest()
            match.replay_download_status = "downloaded"
            match.replay_download_error = None
            match.replay_downloaded_at = utc_now()
            db.commit()
            return True
        except Exception as exc:
            if temporary.exists():
                temporary.unlink()
            match.replay_download_url = url
            match.replay_download_status = "error"
            match.replay_download_error = str(exc)[:1000]
            db.commit()
            logger.warning("Не удалось сохранить replay %s: %s", match.match_id, exc)
            return False
