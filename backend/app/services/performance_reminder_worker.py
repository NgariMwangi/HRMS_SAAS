"""Small hourly reminder worker using the project's async database infrastructure."""
import asyncio
import logging
import os

from app.services.performance_reminders import run

logger = logging.getLogger("performance.reminders")


async def serve():
    interval = max(300, int(os.environ.get("PERFORMANCE_REMINDER_INTERVAL_SECONDS", "3600")))
    while True:
        try:
            await run()
        except Exception:
            logger.exception("Performance reminder pass failed; will retry")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
