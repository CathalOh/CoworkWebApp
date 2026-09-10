from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.base import Base, TimestampMixin, UUIDMixin


class Conversation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="SET NULL"))
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("workspaces.id", ondelete="SET NULL"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    title: Mapped[str | None] = mapped_column(Text)
    shared_with_team: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("teams.id"))
    permission_mode: Mapped[str] = mapped_column(String(32), default="default")
    connector_ids: Mapped[list[Any] | None] = mapped_column()
    skill_names: Mapped[list[Any] | None] = mapped_column()
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class Message(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user|assistant|system
    seq: Mapped[int] = mapped_column(Integer)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    text_cache: Mapped[str | None] = mapped_column(Text)  # denormalized text for search/FTS
    embedding_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # null => not yet embedded


class ContentBlock(UUIDMixin, Base):
    __tablename__ = "content_blocks"
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    block_type: Mapped[str] = mapped_column(String(32))  # text|thinking|tool_use|tool_result|image
    content: Mapped[dict[str, Any]] = mapped_column()
    ord: Mapped[int] = mapped_column(Integer)


class ToolCall(UUIDMixin, Base):
    __tablename__ = "tool_calls"
    message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("messages.id", ondelete="SET NULL"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    tool_use_id: Mapped[str] = mapped_column(Text, index=True)
    tool_name: Mapped[str] = mapped_column(Text)
    input: Mapped[dict[str, Any] | None] = mapped_column()
    mcp_server: Mapped[str | None] = mapped_column(Text)


class ToolResult(UUIDMixin, Base):
    __tablename__ = "tool_results"
    tool_use_id: Mapped[str] = mapped_column(Text, index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    output: Mapped[dict[str, Any] | None] = mapped_column()
    is_error: Mapped[bool] = mapped_column(Boolean, default=False)
    bytes: Mapped[int] = mapped_column(BigInteger, default=0)


class Artifact(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="SET NULL"))
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(32))  # html|react|markdown|svg|mermaid|code
    title: Mapped[str] = mapped_column(Text)
    latest_version: Mapped[int] = mapped_column(Integer, default=1)
    live_source: Mapped[dict[str, Any] | None] = mapped_column()  # Live Artifacts: connector/tool refresh spec


class ArtifactVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "artifact_versions"
    artifact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("artifacts.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    storage: Mapped[dict[str, Any] | None] = mapped_column()  # persistent artifact storage (<=20MB) manifest


class Attachment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "attachments"
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(Text)
    object_key: Mapped[str] = mapped_column(Text)
    mime: Mapped[str | None] = mapped_column(String(255))
    bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    scan_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|clean|rejected
