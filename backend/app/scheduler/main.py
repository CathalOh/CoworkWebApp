"""Standalone scheduler loop (used by the `scheduler` compose service). It only enqueues; workers execute."""
from __future__ import annotations

import asyncio

from app.observability.logging import configure_logging, get_logger
from app.tasks.worker import scheduler_tick

log = get_logger("scheduler")


async def main() -> None:
    configure_logging()
    log.info("scheduler_started")
    while True:
        try:
            n = await scheduler_tick({})
            if n:
                log.info("schedules_fired", count=n)
        except Exception as exc:
            log.error("scheduler_tick_failed", error=str(exc))
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
