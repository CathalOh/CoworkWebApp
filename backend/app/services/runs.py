"""Run creation: quota/concurrency/kill-switch pre-flight, persistence, and enqueue."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AgentSession, Conversation, Message, Run, User
from app.security.audit import record_audit
from app.services.capabilities import get_capabilities
from app.services.usage import spend_for_user


class RunRejected(Exception):
    def __init__(self, reason: str, status: int = 409):
        super().__init__(reason)
        self.reason, self.status = reason, status


async def start_run(db: AsyncSession, *, conversation: Conversation, user: User, prompt: str, permission_mode: str | None,
                    config: dict[str, Any] | None, request_id: str | None, ip: str | None, task_id: uuid.UUID | None = None) -> Run:
    s = get_settings()
    caps = await get_capabilities(db)
    if not caps.get("new_runs", True):
        raise RunRejected("new runs are paused by an administrator", 503)
    active = (await db.execute(select(func.count(Run.id)).where(Run.user_id == user.id,
                                                                Run.status.in_(("queued", "running", "waiting_approval", "waiting_elicitation"))))).scalar_one()
    if active >= s.max_concurrent_runs_per_user:
        raise RunRejected("per-user concurrent run limit reached", 429)
    quota = (config or {}).get("monthly_quota_usd")
    if quota is not None and await spend_for_user(db, user.id) >= float(quota):
        raise RunRejected("monthly cost quota exhausted", 402)
    mode = permission_mode or conversation.permission_mode or s.default_permission_mode
    if mode == "bypassPermissions":
        raise RunRejected("bypassPermissions is not allowed for user-facing runs", 400)

    session = (await db.execute(select(AgentSession).where(AgentSession.conversation_id == conversation.id)
                                .order_by(AgentSession.created_at.desc()).limit(1))).scalar_one_or_none()
    if session is None:
        session = AgentSession(conversation_id=conversation.id, runtime=s.agent_runtime, model_id=s.claude_agent_model)
        db.add(session)
        await db.flush()
    last = (await db.execute(select(Message.seq).where(Message.conversation_id == conversation.id)
                             .order_by(Message.seq.desc()).limit(1))).scalar_one_or_none() or 0
    run = Run(session_id=session.id, conversation_id=conversation.id, user_id=user.id, status="queued", permission_mode=mode,
              prompt=prompt, config=config or {}, request_id=request_id, task_id=task_id)
    db.add(run)
    await db.flush()
    from app.models import ContentBlock

    msg = Message(conversation_id=conversation.id, role="user", seq=last + 1, run_id=run.id, text_cache=prompt[:100_000])
    db.add(msg)
    await db.flush()
    db.add(ContentBlock(message_id=msg.id, block_type="text", content={"type": "text", "text": prompt}, ord=0))
    await record_audit(db, action="run.created", actor_id=user.id, entity_type="run", entity_id=run.id, request_id=request_id, ip=ip,
                       after={"conversation_id": str(conversation.id), "permission_mode": mode, "prompt_chars": len(prompt)})
    return run
