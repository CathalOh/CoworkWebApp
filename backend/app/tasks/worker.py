"""arq worker: agent runs, embeddings/memory, scheduled-task firing, retention sweeps.

Run with: arq app.tasks.worker.WorkerSettings
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from sqlalchemy import delete

from app.config import get_settings
from app.db import db_session
from app.models import AppLog, LlmRequestLog, OAuthState, RunEvent
from app.models.base import utcnow
from app.observability.logging import configure_logging, get_logger

log = get_logger("worker")
_run_semaphore: asyncio.Semaphore | None = None


def _sem() -> asyncio.Semaphore:
    global _run_semaphore
    if _run_semaphore is None:
        _run_semaphore = asyncio.Semaphore(get_settings().max_concurrent_runs_global)
    return _run_semaphore


async def execute_run(ctx: dict[str, Any], run_id: str) -> dict[str, Any]:
    from app.orchestration.host import execute_run as _exec

    async with _sem():
        log.info("run_start", run_id=run_id)
        return await _exec(run_id)


async def embed_conversation(ctx: dict[str, Any], conversation_id: str) -> int:
    import uuid

    from app.services.memory import embed_pending_messages, generate_memories_from_conversation

    async with db_session() as db:
        n = await embed_pending_messages(db, uuid.UUID(conversation_id))
        await generate_memories_from_conversation(db, uuid.UUID(conversation_id))
        await db.commit()
    return n


async def fire_schedule(ctx: dict[str, Any], schedule_id: str) -> str | None:
    from app.scheduler.service import fire

    async with db_session() as db:
        run_id = await fire(db, schedule_id)
        await db.commit()
    if run_id:
        from app.tasks.queue import enqueue

        await enqueue("execute_run", run_id)
    return run_id


async def retention_sweep(ctx: dict[str, Any]) -> dict[str, int]:
    """Retention: app_logs 30d, llm_request_logs 180d, run_events 7d, oauth states expired. audit_events are never
    deleted here (partition drop by an admin with the retention runbook)."""
    now = utcnow()
    out: dict[str, int] = {}
    async with db_session() as db:
        for name, model, col, days in (("app_logs", AppLog, AppLog.ts, 30), ("llm_request_logs", LlmRequestLog, LlmRequestLog.ts, 180),
                                        ("run_events", RunEvent, RunEvent.ts, 7)):
            r = await db.execute(delete(model).where(col < now - timedelta(days=days)))
            out[name] = r.rowcount or 0
        r = await db.execute(delete(OAuthState).where(OAuthState.expires_at < now))
        out["oauth_states"] = r.rowcount or 0
        await db.commit()
    return out


async def scheduler_tick(ctx: dict[str, Any]) -> int:
    from app.scheduler.service import due_schedules

    async with db_session() as db:
        due = await due_schedules(db)
        for sch in due:
            from app.tasks.queue import enqueue

            await enqueue("fire_schedule", str(sch.id))
        await db.commit()
    return len(due)


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging()
    log.info("worker_started", runtime=get_settings().agent_runtime, provider=get_settings().model_provider)


async def shutdown(ctx: dict[str, Any]) -> None:
    log.info("worker_stopped")


def _settings():
    from arq import cron
    from arq.connections import RedisSettings

    class WorkerSettings:
        functions = [execute_run, embed_conversation, fire_schedule, retention_sweep, scheduler_tick]
        cron_jobs = [cron(scheduler_tick, minute=set(range(0, 60)), second=5), cron(retention_sweep, hour=3, minute=15)]
        on_startup = startup
        on_shutdown = shutdown
        redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
        max_jobs = get_settings().max_concurrent_runs_global + 8
        job_timeout = 60 * 60 * 3
        keep_result = 3600

    return WorkerSettings


try:
    WorkerSettings = _settings()
except Exception:  # pragma: no cover - arq missing in some test envs
    WorkerSettings = None
