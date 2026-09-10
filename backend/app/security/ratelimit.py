"""Fixed-window per-principal rate limiting on Redis (falls back to in-memory when Redis is absent)."""
from __future__ import annotations

import time
from collections import defaultdict

_local: dict[str, list[float]] = defaultdict(list)


async def check_rate_limit(redis, key: str, limit: int, window_seconds: int = 60) -> bool:
    now = time.time()
    if redis is None:
        bucket = _local[key]
        bucket[:] = [t for t in bucket if now - t < window_seconds]
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True
    slot = int(now // window_seconds)
    rk = f"rl:{key}:{slot}"
    n = await redis.incr(rk)
    if n == 1:
        await redis.expire(rk, window_seconds + 1)
    return n <= limit
