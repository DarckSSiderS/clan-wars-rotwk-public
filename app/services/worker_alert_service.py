import logging
from datetime import datetime

import aiohttp

from app.config import settings
from app.core.time import as_utc


logger = logging.getLogger(__name__)


class WorkerAlertService:
    def __init__(self, webhook_url: str | None = None) -> None:
        self.webhook_url = (
            settings.WORKER_ALERT_WEBHOOK_URL
            if webhook_url is None
            else webhook_url
        ).strip()

    async def _post(self, payload: dict[str, object]) -> bool:
        timeout = aiohttp.ClientTimeout(total=settings.WORKER_ALERT_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.webhook_url, json=payload) as response:
                response.raise_for_status()
        return True

    async def _notify(self, payload: dict[str, object]) -> bool:
        if not self.webhook_url:
            return False
        try:
            return bool(await self._post(payload))
        except Exception as exc:
            logger.warning(
                "Worker alert webhook delivery failed (%s)",
                exc.__class__.__name__,
            )
            return False

    async def notify_failure(
        self,
        *,
        consecutive_failures: int,
        occurred_at: datetime,
    ) -> bool:
        return await self._notify(
            {
                "service": "clanwar-campaign-worker",
                "code": "campaign_worker_cycle_failed",
                "status": "error",
                "occurred_at": as_utc(occurred_at).isoformat(),
                "consecutive_failures": int(consecutive_failures),
            }
        )

    async def notify_recovery(self, *, occurred_at: datetime) -> bool:
        return await self._notify(
            {
                "service": "clanwar-campaign-worker",
                "code": "campaign_worker_recovered",
                "status": "ok",
                "occurred_at": as_utc(occurred_at).isoformat(),
            }
        )
