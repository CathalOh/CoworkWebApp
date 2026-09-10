"""Server-side sessions: an opaque id in a signed HttpOnly cookie; session data in Redis (or memory in tests)."""
from __future__ import annotations

import json
import secrets
import time
from typing import Any

from itsdangerous import BadSignature, URLSafeSerializer

from app.config import get_settings

_mem: dict[str, tuple[float, dict[str, Any]]] = {}


def _signer() -> URLSafeSerializer:
    return URLSafeSerializer(get_settings().secret_key, salt="session")


class SessionStore:
    def __init__(self, redis=None) -> None:
        self.redis = redis
        self.ttl = get_settings().session_ttl_seconds

    async def create(self, data: dict[str, Any]) -> str:
        sid = secrets.token_urlsafe(32)
        await self.save(sid, data)
        return sid

    async def save(self, sid: str, data: dict[str, Any]) -> None:
        if self.redis is not None:
            await self.redis.set(f"sess:{sid}", json.dumps(data, default=str), ex=self.ttl)
        else:
            _mem[sid] = (time.time() + self.ttl, data)

    async def load(self, sid: str) -> dict[str, Any] | None:
        if self.redis is not None:
            raw = await self.redis.get(f"sess:{sid}")
            if raw:
                await self.redis.expire(f"sess:{sid}", self.ttl)  # sliding expiry
                return json.loads(raw)
            return None
        item = _mem.get(sid)
        if not item or item[0] < time.time():
            _mem.pop(sid, None)
            return None
        return item[1]

    async def delete(self, sid: str) -> None:
        if self.redis is not None:
            await self.redis.delete(f"sess:{sid}")
        else:
            _mem.pop(sid, None)


def sign_cookie(sid: str) -> str:
    return _signer().dumps(sid)


def unsign_cookie(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _signer().loads(value)
    except BadSignature:
        return None
