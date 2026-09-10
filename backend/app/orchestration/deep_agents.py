"""DeepAgentsRuntime: LangChain Deep Agents (LangGraph) fallback behind the same AgentRuntime seam.

Activated when Decision Gate A fails (ILIAD is OpenAI-compatible only). Maps RunConfig onto
create_deep_agent(): filesystem backend rooted at the workspace, subagents from cfg.agents,
interrupt_on for approvals, a checkpointer for durable resume, and MCP tools via langchain-mcp-adapters.
Imports are lazy so the primary path never needs the optional dependency set.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from app.config import get_settings
from app.orchestration import policy
from app.orchestration.base import RunConfig, RuntimeHooks

MUTATING_TOOLS = ("write_file", "edit_file", "execute")


class DeepAgentsRuntime:
    name = "deep_agents"

    def __init__(self) -> None:
        self._interrupted: set[str] = set()

    async def run(self, cfg: RunConfig, hooks: RuntimeHooks) -> dict[str, Any]:
        try:
            from deepagents import create_deep_agent
            from langchain_openai import ChatOpenAI
            from langgraph.checkpoint.memory import MemorySaver
            from langgraph.types import Command
        except ImportError as exc:  # pragma: no cover
            await hooks.emit("error", {"message": f"deep agents runtime not installed: {exc}"})
            return {"session_id": None, "is_error": True, "result": str(exc), "total_cost_usd": 0, "usage": {}}

        s = get_settings()
        model = ChatOpenAI(
            model=cfg.model or s.claude_agent_model,
            base_url=cfg.env.get("OPENAI_BASE_URL") or s.litellm_base_url,
            api_key=cfg.env.get("OPENAI_API_KEY") or s.litellm_api_key or "none",
            streaming=True,
        )
        tools = await self._mcp_tools(cfg)
        subagents = [
            {"name": n, "description": a.get("description", n), "prompt": a.get("prompt", ""), "tools": a.get("tools")}
            for n, a in cfg.agents.items()
        ]
        agent = create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=cfg.system_prompt,
            subagents=subagents or None,
            interrupt_on={t: True for t in MUTATING_TOOLS},
            checkpointer=MemorySaver(),
        )
        thread_id = cfg.resume_session_id or f"da-{uuid.uuid4()}"
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": (cfg.max_turns or 50) * 2}
        await hooks.emit("run_started", {"session_id": thread_id, "model": cfg.model, "tools": [t.name for t in tools]})

        payload: Any = {"messages": [{"role": "user", "content": cfg.prompt}]}
        text_parts: list[str] = []
        usage = {"input_tokens": 0, "output_tokens": 0}
        always: set[str] = set()
        while True:
            if hooks.is_interrupted():
                await hooks.emit("interrupted", {})
                return {"session_id": thread_id, "is_error": False, "result": "interrupted", "total_cost_usd": 0, "usage": usage}
            async for event in agent.astream_events(payload, config=config, version="v2"):
                kind = event.get("event")
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    txt = chunk.content if isinstance(chunk.content, str) else "".join(
                        c.get("text", "") for c in chunk.content if isinstance(c, dict))
                    if txt:
                        text_parts.append(txt)
                        await hooks.emit("assistant_text", {"text": txt, "delta": True})
                    um = getattr(chunk, "usage_metadata", None)
                    if um:
                        usage["input_tokens"] += um.get("input_tokens", 0)
                        usage["output_tokens"] += um.get("output_tokens", 0)
                elif kind == "on_tool_start":
                    await hooks.emit("tool_use", {"tool_use_id": event.get("run_id"), "name": event.get("name"),
                                                  "input": event["data"].get("input")})
                elif kind == "on_tool_end":
                    out = event["data"].get("output")
                    cleaned, _ = policy.sanitize_tool_result(str(out), max_len=20_000)
                    await hooks.emit("tool_result", {"tool_use_id": event.get("run_id"), "content": cleaned, "is_error": False})
            state = agent.get_state(config)
            interrupts = [i for t in state.tasks for i in getattr(t, "interrupts", [])]
            if not interrupts:
                break
            decisions = []
            for intr in interrupts:
                req = intr.value if isinstance(intr.value, dict) else {"value": intr.value}
                actions = req.get("action_requests") or [req]
                for a in actions:
                    name = a.get("name") or a.get("action", "tool")
                    args = a.get("args") or a.get("input") or {}
                    d = policy.evaluate(name, args, workspace_path=cfg.workspace_path, permission_mode=cfg.permission_mode,
                                        allowed_tools=cfg.allowed_tools, disallowed_tools=cfg.disallowed_tools,
                                        always_allowed=always, deletion_protection=cfg.deletion_protection)
                    if d.verdict == "allow":
                        decisions.append({"type": "approve"})
                        continue
                    if d.verdict == "deny":
                        decisions.append({"type": "reject", "message": d.reason})
                        continue
                    tuid = f"tu_{uuid.uuid4().hex[:8]}"
                    dec, rewrite = await hooks.request_approval(tuid, name, args, {"reason": d.reason, "category": d.category})
                    if dec == "always_allow" and d.category != "delete":
                        always.add(name)
                    if dec in ("allow", "always_allow"):
                        decisions.append({"type": "edit", "edited_action": {"name": name, "args": rewrite}} if rewrite else {"type": "approve"})
                    else:
                        decisions.append({"type": "reject", "message": "denied by user"})
            payload = Command(resume={"decisions": decisions})
        text = "".join(text_parts)
        await hooks.emit("result", {"total_cost_usd": None, "usage": usage, "session_id": thread_id, "text": text})
        return {"session_id": thread_id, "is_error": False, "result": text, "total_cost_usd": None, "usage": usage}

    async def _mcp_tools(self, cfg: RunConfig) -> list[Any]:
        if not cfg.mcp_servers:
            return []
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
        except ImportError:
            return []
        conns = {}
        for name, c in cfg.mcp_servers.items():
            t = c.get("type", "stdio")
            if t in ("http", "streamable-http"):
                conns[name] = {"transport": "streamable_http", "url": c["url"], "headers": c.get("headers", {})}
            elif t == "sse":
                conns[name] = {"transport": "sse", "url": c["url"], "headers": c.get("headers", {})}
            elif t == "stdio" or "command" in c:
                conns[name] = {"transport": "stdio", "command": c["command"], "args": c.get("args", []), "env": c.get("env")}
        if not conns:
            return []
        client = MultiServerMCPClient(conns)
        tools = await client.get_tools()
        for t in tools:  # keep mcp__<server>__<tool> naming so allowlists are runtime-agnostic
            if not t.name.startswith("mcp__"):
                server = getattr(t, "metadata", {}).get("server") if getattr(t, "metadata", None) else None
                if server:
                    t.name = f"mcp__{server}__{t.name}"
        avail = [t for t in cfg.tools + cfg.allowed_tools if t.startswith("mcp__")]
        return [t for t in tools if not avail or policy.matches_any(t.name, avail)]

    async def interrupt(self, run_id: str) -> None:
        self._interrupted.add(run_id)


def _dump(o: Any) -> str:
    return json.dumps(o, default=str)
