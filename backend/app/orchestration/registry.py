from __future__ import annotations

from app.config import get_settings
from app.orchestration.base import AgentRuntime

_instances: dict[str, AgentRuntime] = {}


def get_runtime(name: str | None = None) -> AgentRuntime:
    name = name or get_settings().agent_runtime
    if name not in _instances:
        if name == "agent_sdk":
            from app.orchestration.agent_sdk import AgentSdkRuntime

            _instances[name] = AgentSdkRuntime()
        elif name == "deep_agents":
            from app.orchestration.deep_agents import DeepAgentsRuntime

            _instances[name] = DeepAgentsRuntime()
        elif name == "mock":
            from app.orchestration.mock import MockRuntime

            _instances[name] = MockRuntime()
        else:
            raise ValueError(f"unknown runtime {name}")
    return _instances[name]
