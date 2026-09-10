from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORM


class ConnectorOut(ORM):
    id: uuid.UUID
    name: str
    display_name: str
    description: str | None
    transport: str
    url: str | None
    auth_type: str
    required_scopes: list[Any] | None
    risk_class: str
    allowed_tools: list[Any] | None
    approved: bool
    enabled: bool
    team_ids: list[Any] | None
    status: str | None = None  # per-user: connected|needs-auth|disabled|none


class ConnectorIn(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9_-]{2,64}$")
    display_name: str
    description: str | None = None
    transport: Literal["http", "sse", "stdio", "sdk"]
    url: str | None = None
    command: dict[str, Any] | None = None
    auth_type: Literal["none", "oauth", "static_header"] = "none"
    oauth: dict[str, Any] | None = None
    required_scopes: list[str] | None = None
    risk_class: Literal["low", "medium", "high"] = "medium"
    allowed_tools: list[str] | None = None
    denied_tools: list[str] | None = None
    approved: bool = False
    enabled: bool = True
    team_ids: list[uuid.UUID] | None = None
    egress_hosts: list[str] | None = None


class SkillIn(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{2,64}$")
    description: str | None = None
    body: str
    allowed_tools: list[str] | None = None
    scope: Literal["user", "team", "org"] = "user"
    team_id: uuid.UUID | None = None


class SkillOut(ORM):
    id: uuid.UUID
    name: str
    description: str | None
    body: str
    allowed_tools: list[Any] | None
    scope: str
    owner_id: uuid.UUID | None
    team_id: uuid.UUID | None
    enabled: bool
    updated_at: datetime


class PluginIn(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9_-]{2,64}$")
    version: str = "0.1.0"
    manifest: dict[str, Any]
    scope: Literal["org", "team"] = "org"
    team_id: uuid.UUID | None = None
    approved: bool = False
    enabled: bool = True


class PluginOut(ORM):
    id: uuid.UUID
    name: str
    version: str
    manifest: dict[str, Any]
    scope: str
    team_id: uuid.UUID | None
    approved: bool
    enabled: bool


class MemoryIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    project_id: uuid.UUID | None = None
    memory_type: Literal["fact", "preference", "summary"] = "fact"


class MemoryOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID | None
    content: str
    memory_type: str
    created_at: datetime


class ArtifactIn(BaseModel):
    kind: Literal["html", "react", "markdown", "svg", "mermaid", "code"]
    title: str = Field(max_length=200)
    content: str
    conversation_id: uuid.UUID | None = None
    live_source: dict[str, Any] | None = None


class ArtifactOut(ORM):
    id: uuid.UUID
    conversation_id: uuid.UUID | None
    kind: str
    title: str
    latest_version: int
    live_source: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class ArtifactVersionOut(ORM):
    version: int
    content: str
    storage: dict[str, Any] | None
    created_at: datetime


class TaskIn(BaseModel):
    name: str = Field(max_length=200)
    prompt: str
    config: dict[str, Any] = Field(default_factory=dict)


class TaskOut(ORM):
    id: uuid.UUID
    name: str
    prompt: str
    config: dict[str, Any] | None
    status: str
    last_run_id: uuid.UUID | None
    created_at: datetime


class ScheduleIn(BaseModel):
    task_id: uuid.UUID
    cron: str
    timezone: str = "UTC"
    permission_mode: Literal["dontAsk", "acceptEdits", "plan", "default"] = "dontAsk"
    enabled: bool = True


class ScheduleOut(ORM):
    id: uuid.UUID
    task_id: uuid.UUID
    cron: str
    timezone: str
    permission_mode: str
    next_run: datetime | None
    last_fired_at: datetime | None
    enabled: bool


class BundleIn(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9_-]{2,64}$")
    manifest: dict[str, Any]
    enabled: bool = True


class BundleOut(ORM):
    id: uuid.UUID
    name: str
    manifest: dict[str, Any]
    enabled: bool


class CapabilityIn(BaseModel):
    key: str
    enabled: bool
    reason: str | None = None
