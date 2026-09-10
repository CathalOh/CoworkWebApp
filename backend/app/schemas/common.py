from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


class Problem(BaseModel):
    """RFC 9457 application/problem+json"""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    request_id: str | None = None


class UserOut(ORM):
    id: uuid.UUID
    email: str
    display_name: str | None
    roles: list[str] = Field(default_factory=list)
    teams: list[uuid.UUID] = Field(default_factory=list)
    csrf_token: str | None = None


class TeamOut(ORM):
    id: uuid.UUID
    name: str
    created_at: datetime


class TeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MembershipIn(BaseModel):
    user_id: uuid.UUID
    team_role: str = "member"


class WorkspaceOut(ORM):
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    team_id: uuid.UUID | None
    host_path: str
    quota_bytes: int | None
    network_policy: dict[str, Any] | None
    created_at: datetime


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    team_id: uuid.UUID | None = None
    quota_bytes: int | None = None
    network_policy: dict[str, Any] | None = None


class ProjectOut(ORM):
    id: uuid.UUID
    owner_id: uuid.UUID
    team_id: uuid.UUID | None
    workspace_id: uuid.UUID | None
    bundle_id: uuid.UUID | None
    name: str
    instructions: str | None
    memory_enabled: bool
    created_at: datetime
    updated_at: datetime


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    instructions: str | None = None
    team_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None
    bundle_id: uuid.UUID | None = None
    memory_enabled: bool = True


class ProjectPatch(BaseModel):
    name: str | None = None
    instructions: str | None = None
    workspace_id: uuid.UUID | None = None
    bundle_id: uuid.UUID | None = None
    memory_enabled: bool | None = None


class ProjectFileOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    path: str
    bytes: int
    mime: str | None
    created_at: datetime


class ShareIn(BaseModel):
    team_id: uuid.UUID
    access: str = Field(default="read", pattern="^(read|write)$")
    share_memory: bool = False
