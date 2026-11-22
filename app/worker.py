import asyncio
import logging
import signal

from app.services.scheduler_service import CampaignWorker


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run() -> None:
    worker = CampaignWorker()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, worker.stop)
        except (NotImplementedError, RuntimeError):
            pass
    await worker.run_forever()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Worker interrupted")
