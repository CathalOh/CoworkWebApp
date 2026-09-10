"""ModelProvider seam: the ILIAD boundary.

env() is injected into the agent subprocess (Agent SDK path) or read by the LangChain model (Deep Agents
path). capabilities() is what Decision Gate A records after the spike.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Capabilities:
    messages_api: bool = False
    streaming: bool = False
    tool_use: bool = False
    extended_thinking: bool = False
    prompt_caching: bool = False
    pdf_files_input: bool = False
    structured_output: bool = False
    model_ids: list[str] = field(default_factory=list)


class ModelProvider(Protocol):
    name: str

    def env(self) -> dict[str, str]: ...
    def capabilities(self) -> Capabilities: ...
    async def healthcheck(self) -> tuple[bool, str]: ...
    def runtime_name(self) -> str: ...
