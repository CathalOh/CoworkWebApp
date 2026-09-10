#!/usr/bin/env python
"""Decision Gate A — ILIAD compatibility spike (PRD §14).

Runs a scripted Claude Agent SDK session against ILIAD and records PASS/FAIL per criterion:
  1. streaming text                     4. extended thinking (adaptive)
  2. multi-turn tool use (in-process)   5. prompt caching (cache_read_input_tokens > 0 on 2nd turn)
  3. exact model-ID acceptance          6. structured output (JSON schema)  7. PDF/file input (optional)
Also checks whether ILIAD accepts the SDK's auth header + beta headers (retries with
CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1 if the first attempt 4xx's).

Usage: ILIAD_BASE_URL=https://iliad.internal ILIAD_AUTH_TOKEN=... CLAUDE_AGENT_MODEL=<id> python scripts/iliad_spike.py
Writes docs/spike-results.json. PASS => proceed with AgentSdkRuntime; FAIL => DeepAgentsRuntime + LiteLLM.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

RESULTS: dict[str, dict] = {}


def rec(name: str, ok: bool, detail: str = "") -> None:
    RESULTS[name] = {"ok": ok, "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {('- ' + detail) if detail else ''}")


async def run(env: dict[str, str]) -> None:
    from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, StreamEvent, TextBlock,
                                  ThinkingBlock, ToolUseBlock, create_sdk_mcp_server, tool)

    model = os.environ.get("CLAUDE_AGENT_MODEL", "claude-opus-5")

    @tool("add", "Add two numbers", {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]})
    async def add(args):
        return {"content": [{"type": "text", "text": str(args["a"] + args["b"])}]}

    calc = create_sdk_mcp_server("calc", tools=[add])
    big_system = "You are a spike agent. " + ("Reference material: " + "lorem ipsum " * 400)  # > cache minimum
    opts = ClaudeAgentOptions(system_prompt=big_system, model=model, mcp_servers={"calc": calc}, allowed_tools=["mcp__calc__add"],
                              permission_mode="dontAsk", env=env, setting_sources=[], include_partial_messages=True,
                              thinking={"type": "adaptive"}, max_turns=6, cwd=str(Path.cwd()))
    t0 = time.time()
    first_token = None
    tool_used = False
    thinking = False
    usages = []
    got_text = ""
    try:
        async with ClaudeSDKClient(options=opts) as client:
            await client.query("Think briefly, then use the calculator tool to add 2 and 3, and reply with the result.")
            async for msg in client.receive_response():
                if isinstance(msg, StreamEvent) and first_token is None and msg.event.get("type") == "content_block_delta":
                    first_token = time.time() - t0
                if isinstance(msg, AssistantMessage):
                    for b in msg.content:
                        if isinstance(b, ToolUseBlock):
                            tool_used = True
                        if isinstance(b, ThinkingBlock):
                            thinking = True
                        if isinstance(b, TextBlock):
                            got_text += b.text
                    if msg.usage:
                        usages.append(msg.usage)
                if isinstance(msg, ResultMessage):
                    rec("model_id_accepted", not msg.is_error or "model" not in (msg.result or "").lower(), f"model={model} subtype={msg.subtype}")
                    rec("auth_and_headers_accepted", msg.api_error_status not in (401, 403, 400), f"api_error_status={msg.api_error_status}")
                    rec("cost_usage_reported", msg.total_cost_usd is not None or bool(msg.usage), f"cost={msg.total_cost_usd}")
            await client.query("Now add 10 and 20 with the tool.")
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage) and msg.usage:
                    usages.append(msg.usage)
    except Exception as exc:
        rec("session", False, f"{type(exc).__name__}: {exc}")
        return
    rec("streaming", first_token is not None, f"ttft={first_token:.2f}s" if first_token else "no stream deltas")
    rec("tool_use_roundtrip", tool_used and "5" in got_text, f"text={got_text[:80]!r}")
    rec("extended_thinking", thinking, "thinking block observed" if thinking else "no thinking block (ILIAD may strip it)")
    cache_hit = any((u.get("cache_read_input_tokens") or 0) > 0 for u in usages)
    rec("prompt_caching", cache_hit, f"usages={usages[-1] if usages else None}")
    rec("latency_acceptable", (first_token or 99) < 5.0, "p95 target < 5s TTFT")
    # structured output via output_format
    try:
        from claude_agent_sdk import query

        so = None
        async for m in query(prompt="Return the user {name:'Ada', age:36} as JSON.", options=ClaudeAgentOptions(
                model=model, env=env, setting_sources=[], permission_mode="dontAsk", max_turns=2,
                output_format={"type": "json_schema", "schema": {"type": "object", "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
                                                                   "required": ["name", "age"]}})):
            if isinstance(m, ResultMessage):
                so = m.structured_output
        rec("structured_output", isinstance(so, dict) and so.get("name") == "Ada", f"{so}")
    except Exception as exc:
        rec("structured_output", False, str(exc))


def main() -> int:
    base = os.environ.get("ILIAD_BASE_URL")
    tok = os.environ.get("ILIAD_AUTH_TOKEN")
    if not base or not tok:
        print("set ILIAD_BASE_URL and ILIAD_AUTH_TOKEN")
        return 2
    env = {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_AUTH_TOKEN": tok, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    if os.environ.get("ILIAD_CUSTOM_HEADERS"):
        env["ANTHROPIC_CUSTOM_HEADERS"] = os.environ["ILIAD_CUSTOM_HEADERS"]
    if os.environ.get("ILIAD_CA_CERT_PATH"):
        env["NODE_EXTRA_CA_CERTS"] = os.environ["ILIAD_CA_CERT_PATH"]
    asyncio.run(run(env))
    if RESULTS.get("auth_and_headers_accepted", {}).get("ok") is False:
        print("retrying with CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1 ...")
        RESULTS.clear()
        asyncio.run(run({**env, "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1"}))
        RESULTS["needs_disable_experimental_betas"] = {"ok": True, "detail": "set ILIAD_DISABLE_EXPERIMENTAL_BETAS=true"}
    must = ("streaming", "tool_use_roundtrip", "model_id_accepted", "auth_and_headers_accepted", "latency_acceptable")
    gate = all(RESULTS.get(k, {}).get("ok") for k in must)
    RESULTS["DECISION_GATE_A"] = {"ok": gate, "detail": "PASS => AgentSdkRuntime (MODEL_PROVIDER=iliad_anthropic); "
                                                         "FAIL => DeepAgentsRuntime + LiteLLM (MODEL_PROVIDER=iliad_openai_compat, AGENT_RUNTIME=deep_agents)"}
    out = Path("docs/spike-results.json")
    out.write_text(json.dumps({"base_url": base, "model": os.environ.get("CLAUDE_AGENT_MODEL"), "results": RESULTS}, indent=2))
    print(f"\nDECISION GATE A: {'PASS' if gate else 'FAIL'} -> {out}")
    return 0 if gate else 1


if __name__ == "__main__":
    sys.exit(main())
