from __future__ import annotations

import httpx

from app.config import get_settings
from app.providers.base import Capabilities


def _parse_headers(raw: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (raw or "").split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


class IliadAnthropicProvider:
    """Primary path: ILIAD exposes the Anthropic Messages API. The SDK honours ANTHROPIC_BASE_URL and
    ANTHROPIC_AUTH_TOKEN; there is no model-name translation and no silent fallback to api.anthropic.com."""

    name = "iliad_anthropic"

    def __init__(self) -> None:
        self.s = get_settings()

    def env(self) -> dict[str, str]:
        s = self.s
        env = {}
        if s.iliad_base_url:
            env["ANTHROPIC_BASE_URL"] = s.iliad_base_url
        if s.iliad_auth_token:
            env["ANTHROPIC_AUTH_TOKEN"] = s.iliad_auth_token
        if s.iliad_custom_headers:
            env["ANTHROPIC_CUSTOM_HEADERS"] = s.iliad_custom_headers
        if s.iliad_disable_experimental_betas:
            env["CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS"] = "1"
        if s.iliad_ca_cert_path:
            env["NODE_EXTRA_CA_CERTS"] = s.iliad_ca_cert_path
        env["ANTHROPIC_MODEL"] = s.claude_agent_model
        return env

    def capabilities(self) -> Capabilities:
        return Capabilities(messages_api=True, streaming=True, tool_use=True, extended_thinking=True,
                            prompt_caching=True, pdf_files_input=True, structured_output=True,
                            model_ids=[self.s.claude_agent_model])

    def runtime_name(self) -> str:
        return "agent_sdk"

    async def healthcheck(self) -> tuple[bool, str]:
        if not self.s.iliad_base_url:
            return False, "ILIAD_BASE_URL not configured"
        headers = {"Authorization": f"Bearer {self.s.iliad_auth_token}", "anthropic-version": "2023-06-01",
                   **_parse_headers(self.s.iliad_custom_headers)}
        try:
            async with httpx.AsyncClient(timeout=5, verify=self.s.iliad_ca_cert_path or True) as c:
                r = await c.get(self.s.iliad_base_url.rstrip("/") + "/v1/models", headers=headers)
            return r.status_code < 500, f"HTTP {r.status_code}"
        except Exception as exc:
            return False, str(exc)


class IliadOpenAICompatProvider:
    """Fallback path: an OpenAI-compatible gateway (LiteLLM in front of ILIAD) feeding DeepAgentsRuntime."""

    name = "iliad_openai_compat"

    def __init__(self) -> None:
        self.s = get_settings()

    def env(self) -> dict[str, str]:
        return {"OPENAI_BASE_URL": self.s.litellm_base_url or "", "OPENAI_API_KEY": self.s.litellm_api_key or "none",
                "OPENAI_MODEL": self.s.claude_agent_model}

    def capabilities(self) -> Capabilities:
        return Capabilities(messages_api=False, streaming=True, tool_use=True, extended_thinking=False,
                            prompt_caching=False, pdf_files_input=False, structured_output=True,
                            model_ids=[self.s.claude_agent_model])

    def runtime_name(self) -> str:
        return "deep_agents"

    async def healthcheck(self) -> tuple[bool, str]:
        if not self.s.litellm_base_url:
            return False, "LITELLM_BASE_URL not configured"
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(self.s.litellm_base_url.rstrip("/") + "/v1/models",
                                headers={"Authorization": f"Bearer {self.s.litellm_api_key}"})
            return r.status_code < 500, f"HTTP {r.status_code}"
        except Exception as exc:
            return False, str(exc)


class MockProvider:
    name = "mock"

    def env(self) -> dict[str, str]:
        s = get_settings()
        env = {"ANTHROPIC_MODEL": s.claude_agent_model}
        if s.iliad_base_url:  # e.g. the mock ILIAD container in compose
            env["ANTHROPIC_BASE_URL"] = s.iliad_base_url
            env["ANTHROPIC_AUTH_TOKEN"] = s.iliad_auth_token or "mock"
        return env

    def capabilities(self) -> Capabilities:
        return Capabilities(messages_api=True, streaming=True, tool_use=True, model_ids=[get_settings().claude_agent_model])

    def runtime_name(self) -> str:
        return get_settings().agent_runtime

    async def healthcheck(self) -> tuple[bool, str]:
        return True, "mock"


def get_model_provider():
    name = get_settings().model_provider
    if name == "iliad_anthropic":
        return IliadAnthropicProvider()
    if name == "iliad_openai_compat":
        return IliadOpenAICompatProvider()
    return MockProvider()
