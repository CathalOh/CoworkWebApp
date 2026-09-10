from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORM

PermissionModeIn = Literal["default", "plan", "acceptEdits", "dontAsk", "auto"]


class ConversationIn(BaseModel):
    title: str | None = None
    project_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None
    permission_mode: PermissionModeIn = "default"
    connector_ids: list[uuid.UUID] | None = None
    skill_names: list[str] | None = None


class ConversationPatch(BaseModel):
    title: str | None = None
    permission_mode: PermissionModeIn | None = None
    connector_ids: list[uuid.UUID] | None = None
    skill_names: list[str] | None = None
    shared_with_team: uuid.UUID | None = None
    archived: bool | None = None
    workspace_id: uuid.UUID | None = None


class ConversationOut(ORM):
    id: uuid.UUID
    title: str | None
    project_id: uuid.UUID | None
    workspace_id: uuid.UUID | None
    user_id: uuid.UUID
    shared_with_team: uuid.UUID | None
    permission_mode: str
    connector_ids: list[Any] | None
    skill_names: list[Any] | None
    archived: bool
    created_at: datetime
    updated_at: datetime


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=200_000)
    permission_mode: PermissionModeIn | None = None
    max_budget_usd: float | None = Field(default=None, ge=0, le=500)
    model: str | None = None
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    attachment_ids: list[uuid.UUID] | None = None


class ContentBlockOut(ORM):
    block_type: str
    content: dict[str, Any]
    ord: int


class MessageOut(ORM):
    id: uuid.UUID
    role: str
    seq: int
    run_id: uuid.UUID | None
    created_at: datetime
    blocks: list[ContentBlockOut] = []


class RunOut(ORM):
    id: uuid.UUID
    conversation_id: uuid.UUID
    status: str
    permission_mode: str
    started_at: datetime | None
    ended_at: datetime | None
    total_cost_usd: float | None
    usage: dict[str, Any] | None
    last_seq: int
    error: str | None
    created_at: datetime


class ApprovalIn(BaseModel):
    tool_use_id: str
    decision: Literal["allow", "deny", "always_allow"]
    rewrite: dict[str, Any] | None = None


class ElicitationIn(BaseModel):
    elicitation_id: str
    action: Literal["accept", "decline", "cancel"] = "accept"
    content: dict[str, Any] | None = None


class ApprovalOut(ORM):
    id: uuid.UUID
    run_id: uuid.UUID
    tool_use_id: str
    tool_name: str
    input: dict[str, Any] | None
    reason: str | None
    decision: str | None
    decided_at: datetime | None
    created_at: datetime
