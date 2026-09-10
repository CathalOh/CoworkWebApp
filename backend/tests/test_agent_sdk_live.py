"""Live check of AgentSdkRuntime (real bundled `claude` CLI) against the mock ILIAD.

Skipped unless MOCK_ILIAD_URL is set (default candidate http://localhost:9100 must be reachable). Exercises the three
Decision-Gate-A basics the adapter depends on: streaming deltas, an in-process MCP tool round-trip, and a mutating tool
routed through can_use_tool (approval), with the file actually written inside the workspace.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import httpx
import pytest

from app.orchestration.base import AgentEvent, RunConfig

MOCK = os.environ.get("MOCK_ILIAD_URL", "http://localhost:9100")


def _reachable() -> bool:
    try:
        return httpx.get(MOCK + "/v1/models", timeout=2).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _reachable(), reason="mock ILIAD not reachable; start tests/mock_iliad on :9100")


class Hooks:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.approvals: list[str] = []
        self.seq = 0

    def is_interrupted(self) -> bool:
        return False

    async def emit(self, type: str, data: dict) -> AgentEvent:
        self.seq += 1
        self.events.append((type, data))
        return AgentEvent(run_id="r", seq=self.seq, type=type, data=data)

    async def request_approval(self, tool_use_id, name, tool_input, context):
        self.approvals.append(name)
        return "allow", None

    async def request_elicitation(self, elicitation_id, payload):
        return {"action": "decline"}


async def _run(prompt: str, ws: str, mcp=None, allowed=None) -> tuple[Hooks, dict]:
    from app.orchestration.agent_sdk import AgentSdkRuntime

    cfg = RunConfig(run_id="r1", conversation_id="c1", user_id="u1", prompt=prompt, workspace_path=ws,
                    system_prompt=f"Test agent. Working directory: {ws}", tools=["Read", "Write", "Bash", "Glob", "Grep"],
                    allowed_tools=allowed or ["Read", "Glob", "Grep"], permission_mode="default", mcp_servers=mcp or {},
                    env={"ANTHROPIC_BASE_URL": MOCK, "ANTHROPIC_AUTH_TOKEN": "mock"}, model="claude-opus-5", max_turns=4,
                    max_budget_usd=1.0, context_manifest={"runtime": "agent_sdk"})
    h = Hooks()
    res = await asyncio.wait_for(AgentSdkRuntime().run(cfg, h), timeout=180)
    return h, res


async def test_streaming_text():
    h, res = await _run("hello from the backbone", tempfile.mkdtemp())
    assert not res["is_error"] and res["session_id"]
    assert any(t == "assistant_text" and d.get("delta") for t, d in h.events)
    assert res["total_cost_usd"] is not None


async def test_in_process_tool_roundtrip():
    h, res = await _run("use the calculator to add 2 and 3", tempfile.mkdtemp(),
                        mcp={"calc": {"type": "sdk_ref", "name": "calc"}}, allowed=["Read", "mcp__calc__*"])
    assert any(t == "tool_use" and d["name"] == "mcp__calc__add" for t, d in h.events)
    assert any(t == "tool_result" and "5" in str(d.get("content")) for t, d in h.events)
    assert "5" in (res.get("result") or "")


async def test_write_requires_approval_and_lands_in_workspace():
    ws = tempfile.mkdtemp()
    h, res = await _run("please write a file", ws)
    assert h.approvals == ["Write"]
    assert (Path(ws) / "notes.md").read_text() == "hello from mock"
    assert not res["is_error"]


async def test_write_outside_workspace_is_hard_blocked():
    """The mock derives the path from the system prompt; with no parsable cwd it targets /ws => PreToolUse denies."""
    from app.orchestration.agent_sdk import AgentSdkRuntime

    ws = tempfile.mkdtemp()
    cfg = RunConfig(run_id="r2", conversation_id="c1", user_id="u1", prompt="please write a file", workspace_path=ws,
                    system_prompt="Test agent with no cwd hint.", tools=["Read", "Write"], allowed_tools=["Read"],
                    permission_mode="acceptEdits", env={"ANTHROPIC_BASE_URL": MOCK, "ANTHROPIC_AUTH_TOKEN": "mock"},
                    model="claude-opus-5", max_turns=4, context_manifest={"runtime": "agent_sdk"})
    h = Hooks()
    await asyncio.wait_for(AgentSdkRuntime().run(cfg, h), timeout=180)
    assert h.approvals == []
    assert any(t == "tool_result" and d.get("denied") and "outside workspace" in d.get("reason", "") for t, d in h.events)
    assert not (Path(ws) / "notes.md").exists()
