"""MockRuntime: deterministic scripted agent used by tests and the walking skeleton (no model needed).

Behaviours (driven by the prompt so e2e tests can steer it):
- default: streams a short assistant reply token by token and finishes with usage/cost.
- prompt contains "write a file": emits a Write tool_use that goes through approval, then a tool_result.
- prompt contains "delete": emits a Bash rm that must be approved (deletion protection path).
- prompt contains "fail": emits an error event.
- prompt contains "slow": sleeps between tokens so reconnect/resume can be exercised.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.orchestration import policy
from app.orchestration.base import RunConfig, RuntimeHooks


class MockRuntime:
    name = "mock"

    def __init__(self) -> None:
        self._interrupts: set[str] = set()

    async def run(self, cfg: RunConfig, hooks: RuntimeHooks) -> dict[str, Any]:
        session_id = cfg.resume_session_id or f"mock-sess-{cfg.conversation_id[:8]}"
        await hooks.emit("run_started", {"session_id": session_id, "model": cfg.model or "mock-model", "tools": cfg.tools,
                                         "mcp_servers": list(cfg.mcp_servers)})
        if cfg.mcp_servers:
            await hooks.emit("mcp_status", {"servers": [
                {"name": n, "status": "needs-auth" if "Authorization" not in (c.get("headers") or {}) and c.get("type") in ("http", "sse") else "connected"}
                for n, c in cfg.mcp_servers.items()]})
        p = cfg.prompt.lower()
        slow = "slow" in p
        if "fail" in p:
            await hooks.emit("error", {"message": "mock failure requested"})
            return {"session_id": session_id, "is_error": True, "result": "mock failure", "total_cost_usd": 0.0, "usage": {}}

        always: set[str] = set()
        text = f"Echo from mock runtime: {cfg.prompt}"
        if "write a file" in p or "delete" in p:
            if "delete" in p:
                tool, tin = "Bash", {"command": f"rm -f {cfg.workspace_path}/old.txt"}
            else:
                tool, tin = "Write", {"file_path": f"{cfg.workspace_path}/notes.md", "content": "hello"}
            tuid = "tu_mock_1"
            await hooks.emit("tool_use", {"tool_use_id": tuid, "name": tool, "input": tin})
            d = policy.evaluate(tool, tin, workspace_path=cfg.workspace_path, permission_mode=cfg.permission_mode,
                                allowed_tools=cfg.allowed_tools, disallowed_tools=cfg.disallowed_tools, always_allowed=always,
                                deletion_protection=cfg.deletion_protection)
            decision = "allow"
            if d.verdict == "ask":
                decision, _rw = await hooks.request_approval(tuid, tool, tin, {"reason": d.reason, "category": d.category})
            elif d.verdict == "deny":
                decision = "deny"
            if decision in ("allow", "always_allow"):
                await hooks.emit("tool_result", {"tool_use_id": tuid, "content": "ok", "is_error": False})
                text = f"Done: {tool} completed."
            else:
                await hooks.emit("tool_result", {"tool_use_id": tuid, "content": "denied", "is_error": True})
                text = f"The {tool} action was not approved, so I stopped."
        for i, tok in enumerate(text.split(" ")):
            if hooks.is_interrupted():
                await hooks.emit("interrupted", {})
                return {"session_id": session_id, "is_error": False, "result": "interrupted", "total_cost_usd": 0.0, "usage": {}}
            await hooks.emit("assistant_text", {"text": tok + (" " if i < len(text.split(" ")) - 1 else ""), "delta": True})
            if slow:
                await asyncio.sleep(0.2)
        usage = {"input_tokens": 120, "output_tokens": len(text.split()), "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        await hooks.emit("result", {"total_cost_usd": 0.0012, "usage": usage, "session_id": session_id, "num_turns": 1, "text": text})
        return {"session_id": session_id, "is_error": False, "result": text, "total_cost_usd": 0.0012, "usage": usage,
                "model_usage": {"mock-model": {"inputTokens": 120, "outputTokens": len(text.split()), "costUSD": 0.0012}}}

    async def interrupt(self, run_id: str) -> None:
        self._interrupts.add(run_id)
