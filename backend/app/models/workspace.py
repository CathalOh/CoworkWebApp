from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.base import Base, TimestampMixin, UUIDMixin


class Workspace(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"
    name: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    team_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("teams.id"))
    host_path: Mapped[str] = mapped_column(Text)
    quota_bytes: Mapped[int | None] = mapped_column(BigInteger)
    network_policy: Mapped[dict[str, Any] | None] = mapped_column()


class Project(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    team_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("teams.id"))
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(Text)
    instructions: Mapped[str | None] = mapped_column(Text)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    bundle_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("project_bundles.id"))


class ProjectFile(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "project_files"
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(Text)
    object_key: Mapped[str] = mapped_column(Text)
    bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    mime: Mapped[str | None] = mapped_column(String(255))


class ProjectShare(UUIDMixin, TimestampMixin, Base):
    """ACL row: a team's access level on a project."""

    __tablename__ = "project_shares"
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"))
    team_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"))
    access: Mapped[str] = mapped_column(String(16), default="read")  # read|write
    share_memory: Mapped[bool] = mapped_column(Boolean, default=False)
