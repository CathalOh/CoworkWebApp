"""Tamper-evident audit log: append-only, HMAC-SHA256 hash chained per stream key.

row_hash = HMAC(key, prev_hash || canonical_json(row_fields)). Chain verification walks a stream in
id order and recomputes. DB-level immutability (REVOKE UPDATE/DELETE + trigger) lives in migration
0001; this module never issues UPDATE/DELETE against audit_events.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.base import utcnow
from app.models.logs import AuditEvent


def _hmac_key() -> bytes:
    s = get_settings()
    if s.audit_hmac_key_b64:
        return base64.b64decode(s.audit_hmac_key_b64)
    if s.is_prod:
        raise RuntimeError("AUDIT_HMAC_KEY_B64 must be set in prod")
    return hashlib.sha256(b"audit:" + s.secret_key.encode()).digest()


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()


def compute_row_hash(prev_hash: bytes | None, fields: dict[str, Any]) -> bytes:
    return hmac.new(_hmac_key(), (prev_hash or b"") + _canonical(fields), hashlib.sha256).digest()


def _canonical_ts(ts: datetime | None) -> str | None:
    """Timezone-normalized so the hash is stable across drivers that drop tzinfo (sqlite) or keep it (Postgres)."""
    if ts is None:
        return None
    if ts.tzinfo is not None:
        ts = ts.astimezone(UTC).replace(tzinfo=None)
    return ts.isoformat()


def _fields(ev: AuditEvent) -> dict[str, Any]:
    return {
        "ts": _canonical_ts(ev.ts),
        "actor_id": str(ev.actor_id) if ev.actor_id else None,
        "actor_type": ev.actor_type,
        "action": ev.action,
        "entity_type": ev.entity_type,
        "entity_id": str(ev.entity_id) if ev.entity_id else None,
        "request_id": ev.request_id,
        "ip": ev.ip,
        "before": ev.before,
        "after": ev.after,
        "stream_key": ev.stream_key,
    }


def stream_key_for(ts: datetime) -> str:
    """One chain per month so each chain lives inside a single partition."""
    return ts.strftime("%Y-%m")


async def record_audit(
    db: AsyncSession,
    *,
    action: str,
    actor_id: uuid.UUID | None,
    actor_type: str = "user",
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    request_id: str | None = None,
    ip: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append one row to the chain. Call inside the same transaction as the operation being audited
    so the audit row and the privileged mutation commit (or roll back) atomically."""
    ts = utcnow()
    key = stream_key_for(ts)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        # serialize chain appends per stream so prev_hash is never stale under concurrency
        from sqlalchemy import text
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": "audit:" + key})
    prev = (
        await db.execute(
            select(AuditEvent.row_hash).where(AuditEvent.stream_key == key).order_by(AuditEvent.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    ev = AuditEvent(
        ts=ts, actor_id=actor_id, actor_type=actor_type, action=action, entity_type=entity_type,
        entity_id=entity_id, request_id=request_id, ip=ip, before=before, after=after,
        stream_key=key, prev_hash=prev,
    )
    ev.row_hash = compute_row_hash(prev, _fields(ev))
    db.add(ev)
    await db.flush()
    return ev


async def verify_chain(db: AsyncSession, stream_key: str | None = None) -> dict[str, Any]:
    """Walk chain(s) and recompute hashes. Returns {ok, checked, streams:{key:{ok, checked, first_bad_id}}}."""
    q = select(AuditEvent).order_by(AuditEvent.stream_key, AuditEvent.id)
    if stream_key:
        q = q.where(AuditEvent.stream_key == stream_key)
    rows = (await db.execute(q)).scalars().all()
    streams: dict[str, dict[str, Any]] = {}
    prev_by_stream: dict[str, bytes | None] = {}
    for ev in rows:
        st = streams.setdefault(ev.stream_key, {"ok": True, "checked": 0, "first_bad_id": None, "head": None})
        if not st["ok"]:
            continue
        expected_prev = prev_by_stream.get(ev.stream_key)
        if (ev.prev_hash or None) != expected_prev or compute_row_hash(ev.prev_hash, _fields(ev)) != ev.row_hash:
            st["ok"] = False
            st["first_bad_id"] = ev.id
            continue
        st["checked"] += 1
        st["head"] = ev.row_hash.hex()
        prev_by_stream[ev.stream_key] = ev.row_hash
    return {"ok": all(s["ok"] for s in streams.values()), "checked": sum(s["checked"] for s in streams.values()), "streams": streams}
