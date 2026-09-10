"""Event bus: Redis Streams keyed by run (offset = seq) with an in-memory fallback for tests.

Resume semantics: the SSE endpoint reads from `after_seq` (Last-Event-ID) forward; the worker XADDs with
explicit IDs `seq-0` so IDs are monotonic and de-duplicated. Streams expire after event_retention_seconds;
the run_events table is the durable copy for anything older.
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from app.config import get_settings
from app.orchestration.base import AgentEvent

TERMINAL_TYPES = {"result", "error", "interrupted"}


def _key(run_id: str) -> str:
    return f"run:{run_id}:events"


def _control_key(run_id: str) -> str:
    return f"run:{run_id}:control"


class InMemoryEventBus:
    def __init__(self) -> None:
        self._events: dict[str, list[AgentEvent]] = defaultdict(list)
        self._cond: dict[str, asyncio.Condition] = defaultdict(asyncio.Condition)
        self._control: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)

    async def publish(self, event: AgentEvent) -> None:
        cond = self._cond[event.run_id]
        async with cond:
            self._events[event.run_id].append(event)
            cond.notify_all()

    async def read(self, run_id: str, after_seq: int = 0, timeout: float | None = None) -> AsyncIterator[AgentEvent]:
        cond = self._cond[run_id]
        idx = 0
        while True:
            async with cond:
                evs = self._events[run_id]
                while idx < len(evs):
                    ev = evs[idx]
                    idx += 1
                    if ev.seq > after_seq:
                        yield ev
                        if ev.type in TERMINAL_TYPES:
                            return
                try:
                    await asyncio.wait_for(cond.wait(), timeout=timeout)
                except TimeoutError:
                    return

    async def send_control(self, run_id: str, msg: dict[str, Any]) -> None:
        await self._control[run_id].put(msg)

    async def receive_control(self, run_id: str, timeout: float | None = None) -> dict[str, Any] | None:
        try:
            return await asyncio.wait_for(self._control[run_id].get(), timeout=timeout)
        except TimeoutError:
            return None

    async def close(self) -> None:
        return None


class RedisEventBus:
    def __init__(self, redis) -> None:
        self.redis = redis
        self.retention = get_settings().event_retention_seconds

    async def publish(self, event: AgentEvent) -> None:
        payload = json.dumps(event.to_dict(), default=str)
        try:
            await self.redis.xadd(_key(event.run_id), {"e": payload}, id=f"{event.seq}-0")
        except Exception as exc:  # duplicate seq (retry) is not fatal
            if "smaller than the target" not in str(exc) and "equal or smaller" not in str(exc):
                raise
        await self.redis.expire(_key(event.run_id), self.retention)

    async def read(self, run_id: str, after_seq: int = 0, timeout: float | None = None) -> AsyncIterator[AgentEvent]:
        last = f"{after_seq}-0" if after_seq else "0-0"
        deadline = asyncio.get_event_loop().time() + timeout if timeout else None
        while True:
            block_ms = 5000
            if deadline is not None:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    return
                block_ms = max(1, int(min(remaining, 5) * 1000))
            res = await self.redis.xread({_key(run_id): last}, block=block_ms, count=200)
            if not res:
                if deadline is not None and asyncio.get_event_loop().time() >= deadline:
                    return
                continue
            for _stream, entries in res:
                for entry_id, fields in entries:
                    last = entry_id if isinstance(entry_id, str) else entry_id.decode()
                    raw = fields.get("e") if isinstance(fields, dict) else None
                    if raw is None:
                        raw = fields.get(b"e")
                    d = json.loads(raw)
                    ev = AgentEvent(run_id=d["run_id"], seq=d["seq"], type=d["type"], data=d["data"],
                                    ts=datetime.fromisoformat(d["ts"]))
                    yield ev
                    if ev.type in TERMINAL_TYPES:
                        return

    async def send_control(self, run_id: str, msg: dict[str, Any]) -> None:
        await self.redis.rpush(_control_key(run_id), json.dumps(msg, default=str))
        await self.redis.expire(_control_key(run_id), self.retention)

    async def receive_control(self, run_id: str, timeout: float | None = None) -> dict[str, Any] | None:
        res = await self.redis.blpop(_control_key(run_id), timeout=int(timeout) if timeout else 0)
        if not res:
            return None
        _k, raw = res
        return json.loads(raw)

    async def close(self) -> None:
        await self.redis.aclose()


_bus: InMemoryEventBus | RedisEventBus | None = None


async def get_event_bus():
    global _bus
    if _bus is None:
        s = get_settings()
        if s.env == "test" or s.redis_url.startswith("memory://"):
            _bus = InMemoryEventBus()
        else:
            import redis.asyncio as aioredis

            _bus = RedisEventBus(aioredis.from_url(s.redis_url, decode_responses=True))
    return _bus


def set_event_bus(bus) -> None:
    global _bus
    _bus = bus
