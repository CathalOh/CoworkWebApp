"""AgentRuntime seam.

Every orchestration backend (Claude Agent SDK, LangChain Deep Agents, the test mock) consumes the same
RunConfig and emits the same AgentEvent stream. Nothing outside this package may import an SDK directly.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

PermissionMode = Literal["default", "plan", "acceptEdits", "dontAsk", "bypassPermissions", "auto"]
EventType = Literal[
    "run_started", "assistant_text", "thinking", "tool_use", "tool_result", "approval_request",
    "approval_decided", "elicitation", "mcp_status", "usage", "result", "error", "interrupted", "status",
]
ApprovalDecision = Literal["allow", "deny", "always_allow"]


@dataclass
class RunConfig:
    run_id: str
    conversation_id: str
    user_id: str
    prompt: str
    workspace_path: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)  # built-in tools available to the model
    allowed_tools: list[str] = field(default_factory=list)  # pre-approved (no prompt); everything else goes through policy/approval
    disallowed_tools: list[str] = field(default_factory=list)
    permission_mode: PermissionMode = "default"
    mcp_servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    skills: list[str] = field(default_factory=list)
    skill_dirs: list[str] = field(default_factory=list)
    plugins: list[dict[str, Any]] = field(default_factory=list)
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)  # sub-agent definitions
    max_budget_usd: float | None = None
    max_turns: int | None = None
    model: str | None = None
    effort: str | None = None
    resume_session_id: str | None = None
    env: dict[str, str] = field(default_factory=dict)  # provider env (ILIAD) injected into the subprocess
    context_manifest: dict[str, Any] = field(default_factory=dict)  # what was loaded (files, instructions, memories)
    task_budget_tokens: int | None = None
    deletion_protection: bool = True


@dataclass
class AgentEvent:
    run_id: str
    seq: int
    type: str
    data: dict[str, Any]
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "seq": self.seq, "type": self.type, "data": self.data, "ts": self.ts.isoformat()}


# The runtime asks the host for decisions through these callbacks; the host (run manager) bridges them to
# the API/UI over Redis. They block until a human answers or a timeout deny fires.
ApprovalHandler = Callable[[str, str, dict[str, Any], dict[str, Any]], Awaitable[tuple[ApprovalDecision, dict[str, Any] | None]]]
ElicitationHandler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class RuntimeHooks(Protocol):
    async def request_approval(self, tool_use_id: str, tool_name: str, tool_input: dict[str, Any], context: dict[str, Any]) -> tuple[ApprovalDecision, dict[str, Any] | None]: ...
    async def request_elicitation(self, elicitation_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def emit(self, type: str, data: dict[str, Any]) -> AgentEvent: ...
    def is_interrupted(self) -> bool: ...


class AgentRuntime(Protocol):
    name: str

    async def run(self, cfg: RunConfig, hooks: RuntimeHooks) -> dict[str, Any]:
        """Execute one turn of the agent; emit events via hooks; return the final result summary
        {"session_id", "total_cost_usd", "usage", "result", "is_error"}."""
        ...

    async def interrupt(self, run_id: str) -> None: ...


class EventSink(Protocol):
    async def publish(self, event: AgentEvent) -> None: ...
    async def read(self, run_id: str, after_seq: int) -> AsyncIterator[AgentEvent]: ...
