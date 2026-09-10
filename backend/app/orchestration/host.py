"""RunHost: executes one run end-to-end inside a worker and bridges runtime callbacks to the API/UI.

Responsibilities: monotonic seq + publish + persist every event; approvals/elicitations over the control
channel (with timeout => deny); interrupt; sandbox lifecycle; message/content-block persistence; usage +
cost records; audit rows for every privileged action; run status transitions.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.db import db_session
from app.models import (
    Approval,
    ContentBlock,
    Conversation,
    Elicitation,
    Message,
    Run,
    RunEvent,
    ToolCall,
    ToolResult,
    UsageRecord,
)
from app.models.base import utcnow
from app.observability import metrics
from app.observability.logging import get_logger, run_id_var
from app.orchestration.base import AgentEvent, ApprovalDecision, RunConfig
from app.orchestration.events import TERMINAL_TYPES, get_event_bus
from app.orchestration.registry import get_runtime
from app.security.audit import record_audit

log = get_logger("run.host")
PRIVILEGED_CATEGORIES = {"delete", "irreversible", "write", "mutating", "screened", "secret", "workspace", "egress"}


class RunHost:
    def __init__(self, run_id: uuid.UUID, cfg: RunConfig, user_id: uuid.UUID, conversation_id: uuid.UUID):
        self.run_id = run_id
        self.cfg = cfg
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.seq = 0
        self._interrupted = False
        self._pending: dict[str, asyncio.Future] = {}
        self._control_task: asyncio.Task | None = None
        self._bus = None
        self.text_parts: list[str] = []
        self.thinking_parts: list[str] = []
        self.blocks: list[dict[str, Any]] = []  # ordered content blocks for the assistant message
        self._event_buffer: list[RunEvent] = []
        self._first_token_at: datetime | None = None
        self._terminal: AgentEvent | None = None  # published only after finalize commits (clients refetch on it)
        self.started_at = utcnow()

    # ---- RuntimeHooks ------------------------------------------------------------------------
    def is_interrupted(self) -> bool:
        return self._interrupted

    async def emit(self, type: str, data: dict[str, Any]) -> AgentEvent:
        self.seq += 1
        ev = AgentEvent(run_id=str(self.run_id), seq=self.seq, type=type, data=data)
        if type == "mcp_status":  # merge connectors the host dropped before the runtime saw them (needs-auth/disabled)
            seen = {srv.get("name") for srv in data.get("servers", [])}
            extra = [st for st in self.cfg.context_manifest.get("connectors", []) if st.get("name") not in seen]
            data = {**data, "servers": list(data.get("servers", [])) + extra}
        if type in TERMINAL_TYPES:
            if self._interrupted and type != "interrupted":
                type, data = "interrupted", {"reason": "interrupted by user", **({"message": data.get("message")} if data.get("message") else {})}
            if self._terminal is None:  # first terminal wins; it is published after the DB state is final
                self._terminal = ev
                self._event_buffer.append(RunEvent(run_id=self.run_id, seq=ev.seq, type=type, data=_jsonable(data), ts=ev.ts))
            self._collect(type, data)
            return ev
        await self._bus.publish(ev)
        self._event_buffer.append(RunEvent(run_id=self.run_id, seq=ev.seq, type=type, data=_jsonable(data), ts=ev.ts))
        if type == "assistant_text" and self._first_token_at is None:
            self._first_token_at = ev.ts
            metrics.observe("run_ttft_seconds", (ev.ts - self.started_at).total_seconds())
        self._collect(type, data)
        if len(self._event_buffer) >= 25 or type in ("tool_use", "approval_request", "result", "error", "interrupted"):
            await self._flush_events()
        return ev

    def _collect(self, type: str, data: dict[str, Any]) -> None:
        if type == "assistant_text":
            if data.get("delta"):
                self.text_parts.append(data.get("text", ""))
            elif data.get("final") and not self.text_parts:
                self.text_parts.append(data.get("text", ""))
        elif type == "thinking" and data.get("delta"):
            self.thinking_parts.append(data.get("text", ""))
        elif type == "tool_use":
            self._close_text_block()
            self.blocks.append({"type": "tool_use", "id": data.get("tool_use_id"), "name": data.get("name"), "input": data.get("input")})
        elif type == "tool_result":
            self.blocks.append({"type": "tool_result", "tool_use_id": data.get("tool_use_id"),
                                "content": data.get("content") if not data.get("denied") else f"[denied: {data.get('reason')}]",
                                "is_error": bool(data.get("is_error") or data.get("denied"))})

    def _close_text_block(self) -> None:
        if self.thinking_parts:
            self.blocks.append({"type": "thinking", "thinking": "".join(self.thinking_parts)})
            self.thinking_parts = []
        if self.text_parts:
            self.blocks.append({"type": "text", "text": "".join(self.text_parts)})
            self.text_parts = []

    async def _flush_events(self) -> None:
        if not self._event_buffer:
            return
        batch, self._event_buffer = self._event_buffer, []
        async with db_session() as db:
            db.add_all(batch)
            await db.execute(Run.__table__.update().where(Run.id == self.run_id).values(last_seq=self.seq))
            await db.commit()

    async def request_approval(self, tool_use_id: str, tool_name: str, tool_input: dict[str, Any], context: dict[str, Any]) -> tuple[ApprovalDecision, dict[str, Any] | None]:
        s = get_settings()
        async with db_session() as db:
            ap = Approval(run_id=self.run_id, tool_use_id=tool_use_id, tool_name=tool_name, input=_jsonable(tool_input),
                          reason=context.get("reason"))
            db.add(ap)
            await db.execute(Run.__table__.update().where(Run.id == self.run_id).values(status="waiting_approval"))
            await record_audit(db, action="tool.approval_requested", actor_id=None, actor_type="service", entity_type="run",
                               entity_id=self.run_id, after={"tool": tool_name, "tool_use_id": tool_use_id,
                                                              "category": context.get("category"), "input": _preview(tool_input)})
            await db.commit()
            approval_id = ap.id
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[tool_use_id] = fut  # registered before the request is visible so a fast answer is never dropped
        await self.emit("approval_request", {"approval_id": str(approval_id), "tool_use_id": tool_use_id, "name": tool_name,
                                             "input": _jsonable(tool_input), "reason": context.get("reason"),
                                             "category": context.get("category"), "timeout_seconds": s.approval_timeout_seconds})
        t0 = utcnow()
        try:
            msg = await asyncio.wait_for(fut, timeout=s.approval_timeout_seconds)
            decision: ApprovalDecision = msg.get("decision", "deny")
            rewrite = msg.get("rewrite")
            decided_by = msg.get("user_id")
        except TimeoutError:
            decision, rewrite, decided_by = "deny", None, None
        finally:
            self._pending.pop(tool_use_id, None)
        metrics.observe("approval_latency_seconds", (utcnow() - t0).total_seconds(), decision=decision)
        async with db_session() as db:
            await db.execute(Approval.__table__.update().where(Approval.id == approval_id).values(
                decision=decision, rewrite=_jsonable(rewrite), decided_at=utcnow(),
                decided_by=uuid.UUID(decided_by) if decided_by else None))
            await db.execute(Run.__table__.update().where(Run.id == self.run_id).values(status="running"))
            await record_audit(db, action=f"tool.{'approved' if decision != 'deny' else 'denied'}",
                               actor_id=uuid.UUID(decided_by) if decided_by else None,
                               actor_type="user" if decided_by else "system", entity_type="run", entity_id=self.run_id,
                               after={"tool": tool_name, "tool_use_id": tool_use_id, "decision": decision,
                                      "reason": "timeout" if decided_by is None and decision == "deny" else context.get("reason"),
                                      "rewrite": bool(rewrite)})
            await db.commit()
        await self.emit("approval_decided", {"tool_use_id": tool_use_id, "decision": decision, "name": tool_name})
        return decision, rewrite

    async def request_elicitation(self, elicitation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        s = get_settings()
        async with db_session() as db:
            db.add(Elicitation(run_id=self.run_id, elicitation_id=elicitation_id, mode=payload.get("mode", "form"),
                               message=payload.get("message"), request_schema=payload.get("requestedSchema") or payload.get("schema"),
                               url=payload.get("url")))
            await db.execute(Run.__table__.update().where(Run.id == self.run_id).values(status="waiting_elicitation"))
            await db.commit()
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[f"elic:{elicitation_id}"] = fut
        await self.emit("elicitation", {"elicitation_id": elicitation_id, **_jsonable(payload)})
        try:
            msg = await asyncio.wait_for(fut, timeout=s.approval_timeout_seconds)
            response = msg.get("response") or {"action": "decline"}
        except TimeoutError:
            response = {"action": "cancel"}
        finally:
            self._pending.pop(f"elic:{elicitation_id}", None)
        async with db_session() as db:
            await db.execute(Elicitation.__table__.update().where(Elicitation.run_id == self.run_id,
                                                                  Elicitation.elicitation_id == elicitation_id)
                             .values(response=_jsonable(response), responded_at=utcnow()))
            await db.execute(Run.__table__.update().where(Run.id == self.run_id).values(status="running"))
            await db.commit()
        return response

    # ---- control channel ---------------------------------------------------------------------
    async def _control_loop(self) -> None:
        while True:
            msg = await self._bus.receive_control(str(self.run_id), timeout=5)
            if msg is None:
                continue
            kind = msg.get("type")
            if kind == "interrupt":
                self._interrupted = True
                try:
                    await get_runtime(self.cfg.context_manifest.get("runtime")).interrupt(str(self.run_id))
                except Exception:
                    pass
            elif kind == "approval":
                fut = self._pending.get(msg.get("tool_use_id", ""))
                if fut and not fut.done():
                    fut.set_result(msg)
            elif kind == "elicitation":
                fut = self._pending.get(f"elic:{msg.get('elicitation_id', '')}")
                if fut and not fut.done():
                    fut.set_result(msg)

    # ---- lifecycle ---------------------------------------------------------------------------
    async def execute(self) -> dict[str, Any]:
        run_id_var.set(str(self.run_id))
        self._bus = await get_event_bus()
        self._control_task = asyncio.create_task(self._control_loop())
        runtime = get_runtime(self.cfg.context_manifest.get("runtime"))
        sandbox = None
        result: dict[str, Any] = {}
        status = "succeeded"
        error: str | None = None
        try:
            async with db_session() as db:
                await db.execute(Run.__table__.update().where(Run.id == self.run_id).values(status="running", started_at=utcnow()))
                await db.commit()
            from app.sandbox.runner import get_sandbox_runner

            sandbox = await get_sandbox_runner().start(str(self.run_id), self.cfg)
            if sandbox and sandbox.env:
                self.cfg.env.update(sandbox.env)
            metrics.inc("runs_started_total", runtime=runtime.name)
            result = await runtime.run(self.cfg, self)
            if self._interrupted:
                status = "cancelled"
            elif result.get("is_error"):
                status, error = "failed", str(result.get("result") or "agent error")
        except Exception as exc:
            log.exception("run_failed", error=str(exc))
            status, error = "failed", str(exc)
            await self.emit("error", {"message": str(exc)})
        finally:
            self._control_task.cancel()
            if sandbox is not None:
                try:
                    await get_sandbox_runner().stop(sandbox)
                except Exception as exc:  # pragma: no cover
                    log.warning("sandbox_stop_failed", error=str(exc))
            try:
                if self._terminal is None:  # runtime returned without a terminal event
                    await self.emit("error" if status == "failed" else "result",
                                    {"message": error} if status == "failed" else {"text": result.get("result"), "usage": result.get("usage"),
                                                                                    "total_cost_usd": result.get("total_cost_usd")})
                await self._finalize(status, error, result)
            except Exception as exc:  # pragma: no cover - never leave clients hanging without a terminal event
                log.exception("finalize_failed", error=str(exc))
                self._terminal = AgentEvent(run_id=str(self.run_id), seq=self._terminal.seq if self._terminal else self.seq + 1,
                                            type="error", data={"message": f"finalize failed: {exc}"})
            finally:
                if self._terminal is not None:
                    await self._bus.publish(self._terminal)
            metrics.inc("runs_finished_total", runtime=runtime.name, status=status)
        return result

    async def _finalize(self, status: str, error: str | None, result: dict[str, Any]) -> None:
        self._close_text_block()
        async with db_session() as db:
            conv = await db.get(Conversation, self.conversation_id)
            last = (await db.execute(select(Message.seq).where(Message.conversation_id == self.conversation_id)
                                     .order_by(Message.seq.desc()).limit(1))).scalar_one_or_none() or 0
            text = "".join(b.get("text", "") for b in self.blocks if b.get("type") == "text")
            if self.blocks or error:
                msg = Message(conversation_id=self.conversation_id, role="assistant", seq=last + 1, run_id=self.run_id,
                              text_cache=(text or error or "")[:100_000])
                db.add(msg)
                await db.flush()
                for i, b in enumerate(self.blocks):
                    db.add(ContentBlock(message_id=msg.id, block_type=b["type"], content=b, ord=i))
                    if b["type"] == "tool_use":
                        name = b.get("name") or ""
                        db.add(ToolCall(message_id=msg.id, run_id=self.run_id, tool_use_id=b.get("id") or "", tool_name=name,
                                        input=b.get("input"), mcp_server=name.split("__")[1] if name.startswith("mcp__") and name.count("__") >= 2 else None))
                    elif b["type"] == "tool_result":
                        db.add(ToolResult(tool_use_id=b.get("tool_use_id") or "", run_id=self.run_id,
                                          output={"content": b.get("content")}, is_error=bool(b.get("is_error")),
                                          bytes=len(str(b.get("content") or ""))))
                if conv and not conv.title and text:
                    conv.title = (self.cfg.prompt.strip().splitlines() or ["Conversation"])[0][:80]
            usage = result.get("usage") or {}
            cost = result.get("total_cost_usd")
            if usage or cost is not None:
                db.add(UsageRecord(run_id=self.run_id, user_id=self.user_id, team_id=conv.shared_with_team if conv else None,
                                   project_id=conv.project_id if conv else None,
                                   model_id=next(iter((result.get("model_usage") or {}).keys()), self.cfg.model),
                                   input_tokens=int(usage.get("input_tokens", 0) or 0), output_tokens=int(usage.get("output_tokens", 0) or 0),
                                   cache_read=int(usage.get("cache_read_input_tokens", 0) or 0),
                                   cache_write=int(usage.get("cache_creation_input_tokens", 0) or 0),
                                   cost_usd=float(cost or 0), ts=utcnow()))
            from app.models import AgentSession, LlmRequestLog

            db.add(LlmRequestLog(run_id=self.run_id, user_id=self.user_id, model_id=self.cfg.model,
                                 request={"prompt_chars": len(self.cfg.prompt), "system_prompt_chars": len(self.cfg.system_prompt),
                                          "tools": self.cfg.allowed_tools, "mcp_servers": list(self.cfg.mcp_servers),
                                          "permission_mode": self.cfg.permission_mode},
                                 response={"status": status, "num_turns": result.get("num_turns"), "text_chars": len(text),
                                           "permission_denials": result.get("permission_denials")},
                                 input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
                                 cache_read_tokens=usage.get("cache_read_input_tokens"), cache_write_tokens=usage.get("cache_creation_input_tokens"),
                                 cost_usd=cost, latency_ms=int((utcnow() - self.started_at).total_seconds() * 1000)))
            run = await db.get(Run, self.run_id)
            if run:
                run.status, run.error, run.ended_at = status, error, utcnow()
                run.total_cost_usd, run.usage, run.last_seq = cost, _jsonable(usage), self.seq
                sess = await db.get(AgentSession, run.session_id)
                if sess and result.get("session_id"):
                    sess.sdk_session_id = result["session_id"]
            db.add_all(self._event_buffer)
            self._event_buffer = []
            await record_audit(db, action=f"run.{status}", actor_id=self.user_id, entity_type="run", entity_id=self.run_id,
                               after={"cost_usd": cost, "usage": _jsonable(usage), "error": error})
            await db.commit()
        # Kick the memory/embedding worker without blocking the response path.
        try:
            from app.tasks.queue import enqueue

            await enqueue("embed_conversation", str(self.conversation_id))
        except Exception:
            pass


def _jsonable(o: Any) -> Any:
    if o is None:
        return None
    try:
        return json.loads(json.dumps(o, default=str))
    except Exception:
        return str(o)


def _preview(o: Any, n: int = 2000) -> Any:
    s = json.dumps(o, default=str)
    return json.loads(s) if len(s) <= n else {"_truncated": s[:n]}


async def execute_run(run_id: str) -> dict[str, Any]:
    """Worker entry point."""
    from app.services.run_builder import build_run_config

    rid = uuid.UUID(run_id)
    async with db_session() as db:
        run = None
        for _attempt in range(5):  # the enqueue may race the producer's commit by a few ms
            run = await db.get(Run, rid)
            if run is not None:
                break
            await asyncio.sleep(0.2)
            db.expire_all()
        if run is None:
            raise ValueError(f"run {run_id} not found")
        if run.status not in ("queued",):
            log.info("run_skip_not_queued", run_id=run_id, status=run.status)
            return {"skipped": True}
        cfg = await build_run_config(db, run)
        user_id, conversation_id = run.user_id, run.conversation_id
        run.config = {**(run.config or {}), "context_manifest": cfg.context_manifest,
                      "tools": cfg.tools, "allowed_tools": cfg.allowed_tools, "mcp_servers": sorted(cfg.mcp_servers)}
        await db.commit()
    host = RunHost(rid, cfg, user_id, conversation_id)
    return await host.execute()
