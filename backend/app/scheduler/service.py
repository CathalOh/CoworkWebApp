"""Cron scheduler: each fire creates an isolated conversation + run using the task's saved prompt, permission
mode, connectors, skills and plugins (mirrors 'each scheduled task runs as its own Cowork session')."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Schedule, Task, User
from app.models.base import utcnow
from app.security.audit import record_audit
from app.services.runs import RunRejected, start_run


def compute_next(cron: str, tz: str = "UTC", base: datetime | None = None) -> datetime:
    base = base or utcnow()
    local = base.astimezone(ZoneInfo(tz))
    nxt = croniter(cron, local).get_next(datetime)
    return nxt.astimezone(UTC)


def validate_cron(cron: str) -> bool:
    return croniter.is_valid(cron)


async def due_schedules(db: AsyncSession) -> list[Schedule]:
    now = utcnow()
    rows = (await db.execute(select(Schedule).where(Schedule.enabled.is_(True), Schedule.next_run <= now))).scalars().all()
    for s in rows:  # advance immediately so a slow worker does not double-fire
        s.last_fired_at = now
        s.next_run = compute_next(s.cron, s.timezone, now)
    return list(rows)


async def run_task_now(db: AsyncSession, task: Task, user: User, permission_mode: str | None = None) -> str:
    cfg = task.config or {}
    conv = Conversation(user_id=user.id, title=f"[task] {task.name} {utcnow():%Y-%m-%d %H:%M}",
                        project_id=uuid.UUID(cfg["project_id"]) if cfg.get("project_id") else None,
                        workspace_id=uuid.UUID(cfg["workspace_id"]) if cfg.get("workspace_id") else None,
                        permission_mode=permission_mode or cfg.get("permission_mode", "dontAsk"),
                        connector_ids=cfg.get("connector_ids"), skill_names=cfg.get("skills"))
    db.add(conv)
    await db.flush()
    run = await start_run(db, conversation=conv, user=user, prompt=task.prompt, permission_mode=conv.permission_mode,
                          config={k: v for k, v in cfg.items() if k in ("max_budget_usd", "max_turns", "model", "effort")},
                          request_id=None, ip=None, task_id=task.id)
    task.status, task.last_run_id = "running", run.id
    return str(run.id)  # caller commits, then enqueues execute_run


async def fire(db: AsyncSession, schedule_id: str) -> str | None:
    sch = await db.get(Schedule, uuid.UUID(schedule_id))
    if not sch or not sch.enabled:
        return None
    task = await db.get(Task, sch.task_id)
    user = await db.get(User, task.owner_id) if task else None
    if not task or not user or user.status != "active":
        return None
    try:
        run_id = await run_task_now(db, task, user, sch.permission_mode)
    except RunRejected as exc:
        await record_audit(db, action="schedule.skipped", actor_id=None, actor_type="system", entity_type="schedule",
                           entity_id=sch.id, after={"reason": exc.reason})
        return None
    await record_audit(db, action="schedule.fired", actor_id=None, actor_type="system", entity_type="schedule", entity_id=sch.id,
                       after={"run_id": run_id, "task_id": str(task.id)})
    return run_id
