"""Org-level capability kill-switches (connectors, web tools, sandbox execution, plugins, new runs, local MCP)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CapabilityFlag

DEFAULTS = {"connectors": True, "web_tools": True, "sandbox_execution": True, "plugins": True, "new_runs": True,
            "local_mcp": False, "memory": True, "artifacts": True, "subagents": True}


async def get_capabilities(db: AsyncSession) -> dict[str, bool]:
    rows = (await db.execute(select(CapabilityFlag))).scalars().all()
    caps = dict(DEFAULTS)
    for r in rows:
        caps[r.key] = bool(r.enabled)
    return caps


async def set_capability(db: AsyncSession, key: str, enabled: bool, reason: str | None, updated_by) -> CapabilityFlag:
    if key not in DEFAULTS:
        raise ValueError(f"unknown capability {key}")
    row = await db.get(CapabilityFlag, key)
    if row is None:
        row = CapabilityFlag(key=key)
        db.add(row)
    row.enabled, row.reason, row.updated_by = enabled, reason, updated_by
    await db.flush()
    return row
