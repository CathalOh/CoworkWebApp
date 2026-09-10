"""Log tables. In Postgres these are RANGE-partitioned by ts and append-only (see migration 0001);
the ORM models describe the row shape only."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Identity, Integer, LargeBinary, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.base import Base, utcnow


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)  # part of the PK in Postgres (partition key)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    actor_type: Mapped[str] = mapped_column(String(16), default="user")  # user|service|system
    action: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    request_id: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(64))
    before: Mapped[dict[str, Any] | None] = mapped_column()
    after: Mapped[dict[str, Any] | None] = mapped_column()
    stream_key: Mapped[str] = mapped_column(String(32), default="main", index=True)
    prev_hash: Mapped[bytes | None] = mapped_column(LargeBinary)
    row_hash: Mapped[bytes] = mapped_column(LargeBinary)


class LlmRequestLog(Base):
    __tablename__ = "llm_request_logs"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)  # part of the PK in Postgres (partition key)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    model_id: Mapped[str | None] = mapped_column(Text)
    request: Mapped[dict[str, Any] | None] = mapped_column()
    response: Mapped[dict[str, Any] | None] = mapped_column()
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    pii_key_id: Mapped[str | None] = mapped_column(Text)  # destroyable key reference for erasure


class AppLog(Base):
    __tablename__ = "app_logs"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)  # part of the PK in Postgres (partition key)
    level: Mapped[str] = mapped_column(String(16))
    logger: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[dict[str, Any] | None] = mapped_column()
    request_id: Mapped[str | None] = mapped_column(Text, index=True)
