"""Backbone extension point (1): custom in-process tools.

Developers register plain async functions with @backbone_tool; they become an in-process MCP server
(`create_sdk_mcp_server`) exposed to the agent as mcp__<server>__<tool>. The Deep Agents runtime wraps the
same registry as LangChain tools, so tools never depend on the orchestration backend.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC
from typing import Any

from app.orchestration.base import RunConfig


@dataclass
class ToolSpec:
    server: str
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    risk: str = "low"  # low|medium|high -> high tools always require approval

    @property
    def full_name(self) -> str:
        return f"mcp__{self.server}__{self.name}"


_REGISTRY: dict[str, list[ToolSpec]] = {}


def backbone_tool(server: str, name: str, description: str, input_schema: dict[str, Any], risk: str = "low"):
    def deco(fn):
        _REGISTRY.setdefault(server, []).append(ToolSpec(server, name, description, input_schema, fn, risk))
        return fn
    return deco


def registry() -> dict[str, list[ToolSpec]]:
    return _REGISTRY


def sdk_servers_for(cfg: RunConfig) -> dict[str, Any]:
    """Materialize registered servers referenced by the run (cfg.mcp_servers entries of type sdk_ref) into
    McpSdkServerConfig instances. Unreferenced servers are not exposed."""
    try:
        from claude_agent_sdk import create_sdk_mcp_server, tool
    except ImportError:
        return {}
    out: dict[str, Any] = {}
    wanted = {n for n, c in cfg.mcp_servers.items() if c.get("type") == "sdk_ref"}
    for server, specs in _REGISTRY.items():
        if server not in wanted:
            continue
        sdk_tools = []
        for spec in specs:
            def _make(spec=spec):
                async def handler(args: dict[str, Any]) -> dict[str, Any]:
                    result = await spec.fn(args)
                    return {"content": [{"type": "text", "text": str(result.get("text", result))}]}
                return tool(spec.name, spec.description, spec.input_schema)(handler)
            sdk_tools.append(_make())
        out[server] = create_sdk_mcp_server(name=server, version="1.0.0", tools=sdk_tools)
    for n in wanted:  # drop unresolved refs so the SDK never sees an unknown config type
        if n not in out:
            cfg.mcp_servers.pop(n, None)
    for n in list(cfg.mcp_servers):
        if cfg.mcp_servers[n].get("type") == "sdk_ref":
            cfg.mcp_servers.pop(n)
    return out


# ---- built-in example tools (safe, deterministic) ----------------------------------------------------
@backbone_tool("calc", "add", "Add two numbers.", {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]})
async def _add(args: dict[str, Any]) -> dict[str, Any]:
    return {"text": str(float(args["a"]) + float(args["b"]))}


@backbone_tool("calc", "multiply", "Multiply two numbers.", {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]})
async def _mul(args: dict[str, Any]) -> dict[str, Any]:
    return {"text": str(float(args["a"]) * float(args["b"]))}


@backbone_tool("backbone", "current_time", "Current UTC time in ISO-8601.", {"type": "object", "properties": {}})
async def _now(_args: dict[str, Any]) -> dict[str, Any]:
    from datetime import datetime

    return {"text": datetime.now(UTC).isoformat()}
