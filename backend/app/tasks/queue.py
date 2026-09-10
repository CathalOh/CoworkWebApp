"""arq job queue (Redis broker). In test/memory mode jobs run inline on the event loop."""
from __future__ import annotations

import asyncio
from typing import Any

from app.config import get_settings

_inline_tasks: set[asyncio.Task] = set()
_pool = None


async def _get_pool():
    global _pool
    if _pool is None:
        from arq import create_pool
        from arq.connections import RedisSettings

        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


async def enqueue(job: str, *args: Any, **kwargs: Any) -> str | None:
    s = get_settings()
    if s.env == "test" or s.redis_url.startswith("memory://"):
        from app.tasks import worker

        fn = getattr(worker, job)
        t = asyncio.create_task(fn({}, *args, **kwargs))
        _inline_tasks.add(t)
        t.add_done_callback(_inline_tasks.discard)
        return f"inline:{id(t)}"
    pool = await _get_pool()
    j = await pool.enqueue_job(job, *args, **kwargs)
    return j.job_id if j else None


async def wait_inline() -> None:
    """Tests: wait for inline jobs to finish."""
    while _inline_tasks:
        await asyncio.gather(*list(_inline_tasks), return_exceptions=True)
