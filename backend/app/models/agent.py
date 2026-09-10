from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.base import Base, TimestampMixin, UUIDMixin

RUN_STATUSES = ("queued", "running", "waiting_approval", "waiting_elicitation", "succeeded", "failed", "cancelled")


class AgentSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_sessions"
    sdk_session_id: Mapped[str | None] = mapped_column(Text, index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    runtime: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[str | None] = mapped_column(Text)
    cwd: Mapped[str | None] = mapped_column(Text)
    sandbox_id: Mapped[str | None] = mapped_column(Text)


class Run(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "runs"
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("agent_sessions.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tasks.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    permission_mode: Mapped[str] = mapped_column(String(32), default="default")
    prompt: Mapped[str] = mapped_column(Text)
    config: Mapped[dict[str, Any] | None] = mapped_column()  # RunConfig snapshot / context manifest
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6))
    usage: Mapped[dict[str, Any] | None] = mapped_column()
    last_seq: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)


class RunEvent(Base):
    """Durable copy of every AgentEvent (Redis holds the hot stream; this is the resume-of-record)."""

    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_run_events_run_seq"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict[str, Any]] = mapped_column()
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Approval(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "approvals"
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    tool_use_id: Mapped[str] = mapped_column(Text, index=True)
    tool_name: Mapped[str] = mapped_column(Text)
    input: Mapped[dict[str, Any] | None] = mapped_column()
    reason: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(String(16))  # allow|deny|always_allow
    rewrite: Mapped[dict[str, Any] | None] = mapped_column()
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Elicitation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "elicitations"
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    elicitation_id: Mapped[str] = mapped_column(Text, index=True)
    mode: Mapped[str] = mapped_column(String(16), default="form")  # form|url
    message: Mapped[str | None] = mapped_column(Text)
    request_schema: Mapped[dict[str, Any] | None] = mapped_column()
    url: Mapped[str | None] = mapped_column(Text)
    response: Mapped[dict[str, Any] | None] = mapped_column()
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Task(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    prompt: Mapped[str] = mapped_column(Text)
    config: Mapped[dict[str, Any] | None] = mapped_column()  # permission_mode, connector_ids, skills, plugins, workspace_id, project_id
    status: Mapped[str] = mapped_column(String(32), default="idle")
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class Schedule(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "schedules"
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    cron: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    permission_mode: Mapped[str] = mapped_column(String(32), default="dontAsk")
    next_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class UsageRecord(UUIDMixin, Base):
    __tablename__ = "usage_records"
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    team_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    model_id: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read: Mapped[int] = mapped_column(Integer, default=0)
    cache_write: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
