from __future__ import annotations

import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, TimestampMixin, UUIDMixin

EMBEDDING_DIM = 1536
VectorType = JSON().with_variant(Vector(EMBEDDING_DIM), "postgresql")


class Skill(UUIDMixin, TimestampMixin, Base):
    """A SKILL.md, stored as frontmatter fields + body; materialized into the session skill dir on demand."""

    __tablename__ = "skills"
    name: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    allowed_tools: Mapped[list[Any] | None] = mapped_column()
    scope: Mapped[str] = mapped_column(String(16), default="user")  # user|team|org
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    team_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("teams.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Plugin(UUIDMixin, TimestampMixin, Base):
    """Bundle of skills + hooks + agents + MCP servers. manifest follows the Claude Code plugin manifest shape."""

    __tablename__ = "plugins"
    name: Mapped[str] = mapped_column(String(128), unique=True)
    version: Mapped[str] = mapped_column(String(32), default="0.1.0")
    manifest: Mapped[dict[str, Any]] = mapped_column()
    scope: Mapped[str] = mapped_column(String(16), default="org")
    team_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("teams.id"))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Memory(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "memories"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    memory_type: Mapped[str] = mapped_column(String(32), default="fact")  # fact|preference|summary
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class Embedding(UUIDMixin, Base):
    __tablename__ = "embeddings"
    ref_type: Mapped[str] = mapped_column(String(32), index=True)  # message|memory|project_file
    ref_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    embedding: Mapped[Any] = mapped_column(VectorType)


class CapabilityFlag(Base):
    """Org-level kill switches: connectors, web tools, sandbox execution, plugins, new runs."""

    __tablename__ = "capability_flags"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    reason: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class ProjectBundle(UUIDMixin, TimestampMixin, Base):
    """A 'cowork project' manifest: skills + tools + connector set + system prompt pack + UI slots."""

    __tablename__ = "project_bundles"
    name: Mapped[str] = mapped_column(String(128), unique=True)
    manifest: Mapped[dict[str, Any]] = mapped_column()
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
