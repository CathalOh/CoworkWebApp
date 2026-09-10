"""Mock ILIAD: a deterministic, scripted subset of the Anthropic Messages API.

Endpoints
  GET  /v1/models    -> {"data": [{"id": "claude-opus-5"}, {"id": "claude-sonnet-5"}]}
  POST /v1/messages  -> Message JSON, or the Anthropic SSE event stream when `stream: true`.

Auth (POST /v1/messages): `Authorization: Bearer <anything>` or `x-api-key: <anything>`; otherwise 401.
GET /v1/models is open so it can serve as a liveness probe.

The reply is chosen from the *last user message text* (see `plan_response`):
  default                                  -> text "Mock ILIAD reply: <prompt>"
  "use the calculator" / "add " + *add tool -> tool_use <tool> {"a": 2, "b": 3}         (stop_reason tool_use)
  "write a file" + Write tool              -> tool_use Write {file_path, content}        (stop_reason tool_use)
  "think"                                  -> thinking block "Let me think..." first, then the text/tool block
  "error500"                               -> HTTP 500 api_error "mock outage"
  "ratelimit"                              -> HTTP 429, retry-after: 1
  last user message carries tool_result    -> "The result is <content>" (or "Wrote the file." after Write)
"""
from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(tags=["anthropic"])

MODELS = ["claude-opus-5", "claude-sonnet-5"]
_msg_counter = itertools.count(1)
_tool_counter = itertools.count(1)


# --------------------------------------------------------------------------------------------------------------
# request inspection helpers
# --------------------------------------------------------------------------------------------------------------
def _text_of(content: Any) -> str:
    """Flatten a message/tool_result `content` (str or list of blocks) into plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif block.get("type") == "tool_result":
                parts.append(_text_of(block.get("content")))
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(p for p in parts if p)


def _last_user_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return _text_of(m.get("content"))
    return ""


def _tool_results(messages: list[dict]) -> list[tuple[str | None, str]]:
    """[(tool name that produced it, result text)] if the last message is a user message with tool_result blocks."""
    if not messages:
        return []
    last = messages[-1]
    if last.get("role") != "user" or not isinstance(last.get("content"), list):
        return []
    names: dict[str, str] = {}
    for m in messages:
        if m.get("role") == "assistant" and isinstance(m.get("content"), list):
            for b in m["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    names[b.get("id", "")] = b.get("name", "")
    return [(names.get(b.get("tool_use_id", "")), _text_of(b.get("content")).strip())
            for b in last["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]


def _find_tool(tools: list[dict], predicate) -> str | None:
    for t in tools or []:
        name = t.get("name") if isinstance(t, dict) else None
        if name and predicate(name):
            return name
    return None


def _cwd_from_system(system: Any) -> str:
    """Claude Code puts 'Working directory: /path' in its system prompt; fall back to the sandbox default /ws."""
    text = system if isinstance(system, str) else _text_of(system)
    m = re.search(r"(?:working directory|cwd)[^\n]*?:\s*`?(/[^\s`'\"]*)", text, re.IGNORECASE)
    if not m:
        return "/ws"
    return m.group(1).rstrip("/") or "/"


def _approx_input_tokens(body: dict) -> int:
    raw = json.dumps({k: body.get(k) for k in ("system", "messages", "tools")}, ensure_ascii=False)
    return max(1, len(raw) // 4)


# --------------------------------------------------------------------------------------------------------------
# scripted planning
# --------------------------------------------------------------------------------------------------------------
@dataclass
class Plan:
    blocks: list[dict] = field(default_factory=list)
    stop_reason: str = "end_turn"
    scenario: str = "default"
    http_error: tuple[int, dict, dict] | None = None  # (status, body, headers)


def _tool_use(name: str, inp: dict) -> dict:
    return {"type": "tool_use", "id": f"toolu_mock_{next(_tool_counter):04d}", "name": name, "input": inp}


def plan_response(body: dict) -> Plan:
    messages = body.get("messages") or []
    tools = body.get("tools") or []
    plan = Plan(scenario="")

    results = _tool_results(messages)
    if results:
        name, text = results[-1]
        if name == "Write":
            plan.blocks.append({"type": "text", "text": "Wrote the file."})
        else:
            plan.blocks.append({"type": "text", "text": f"The result is {text}"})
        plan.scenario = "tool_result"
        return plan

    prompt = _last_user_text(messages)
    low = prompt.lower()

    if "error500" in low:
        plan.scenario = "error500"
        plan.http_error = (500, {"type": "error", "error": {"type": "api_error", "message": "mock outage"}}, {})
        return plan
    if "ratelimit" in low:
        plan.scenario = "ratelimit"
        plan.http_error = (429, {"type": "error", "error": {"type": "rate_limit_error", "message": "mock rate limit"}},
                           {"retry-after": "1"})
        return plan

    if "think" in low:
        plan.blocks.append({"type": "thinking", "thinking": "Let me think...", "signature": "mock-signature"})
        plan.scenario = "thinking+"

    add_tool = _find_tool(tools, lambda n: n.endswith("add"))
    write_tool = _find_tool(tools, lambda n: n == "Write")
    if ("use the calculator" in low or "add " in low) and add_tool:
        plan.blocks.append(_tool_use(add_tool, {"a": 2, "b": 3}))
        plan.stop_reason = "tool_use"
        plan.scenario += "calculator"
    elif "write a file" in low and write_tool:
        cwd = _cwd_from_system(body.get("system"))
        plan.blocks.append(_tool_use("Write", {"file_path": f"{cwd}/notes.md", "content": "hello from mock"}))
        plan.stop_reason = "tool_use"
        plan.scenario += "write"
    else:
        plan.blocks.append({"type": "text", "text": f"Mock ILIAD reply: {prompt}".rstrip()})
        plan.scenario += "text"
    return plan


def _output_tokens(blocks: list[dict]) -> int:
    n = 0
    for b in blocks:
        if b["type"] == "text":
            n += len(b["text"].split())
        elif b["type"] == "thinking":
            n += len(b["thinking"].split())
        elif b["type"] == "tool_use":
            n += len(json.dumps(b["input"]).split()) + 1
    return max(1, n)


def _usage(input_tokens: int, output_tokens: int) -> dict:
    return {"input_tokens": input_tokens, "output_tokens": output_tokens,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}


# --------------------------------------------------------------------------------------------------------------
# SSE streaming
# --------------------------------------------------------------------------------------------------------------
def _frame(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


def _chunks(s: str, words_per_chunk: int = 4) -> list[str]:
    words = s.split(" ")
    return [" ".join(words[i:i + words_per_chunk]) + (" " if i + words_per_chunk < len(words) else "")
            for i in range(0, len(words), words_per_chunk)] or [""]


def _json_chunks(obj: dict, parts: int = 3) -> list[str]:
    raw = json.dumps(obj)
    step = max(1, -(-len(raw) // parts))
    return [raw[i:i + step] for i in range(0, len(raw), step)]


async def _stream(msg_id: str, model: str, plan: Plan, input_tokens: int) -> AsyncIterator[bytes]:
    out_tokens = _output_tokens(plan.blocks)
    yield _frame("message_start", {"type": "message_start", "message": {
        "id": msg_id, "type": "message", "role": "assistant", "model": model, "content": [],
        "stop_reason": None, "stop_sequence": None, "usage": _usage(input_tokens, 1)}})
    yield _frame("ping", {"type": "ping"})
    for index, block in enumerate(plan.blocks):
        if block["type"] == "text":
            yield _frame("content_block_start", {"type": "content_block_start", "index": index,
                                                 "content_block": {"type": "text", "text": ""}})
            for piece in _chunks(block["text"]):
                yield _frame("content_block_delta", {"type": "content_block_delta", "index": index,
                                                     "delta": {"type": "text_delta", "text": piece}})
        elif block["type"] == "thinking":
            yield _frame("content_block_start", {"type": "content_block_start", "index": index,
                                                 "content_block": {"type": "thinking", "thinking": ""}})
            for piece in _chunks(block["thinking"], 2):
                yield _frame("content_block_delta", {"type": "content_block_delta", "index": index,
                                                     "delta": {"type": "thinking_delta", "thinking": piece}})
            yield _frame("content_block_delta", {"type": "content_block_delta", "index": index,
                                                 "delta": {"type": "signature_delta", "signature": block["signature"]}})
        elif block["type"] == "tool_use":
            yield _frame("content_block_start", {"type": "content_block_start", "index": index,
                                                 "content_block": {"type": "tool_use", "id": block["id"],
                                                                   "name": block["name"], "input": {}}})
            for piece in _json_chunks(block["input"]):
                yield _frame("content_block_delta", {"type": "content_block_delta", "index": index,
                                                     "delta": {"type": "input_json_delta", "partial_json": piece}})
        yield _frame("content_block_stop", {"type": "content_block_stop", "index": index})
    yield _frame("message_delta", {"type": "message_delta",
                                   "delta": {"stop_reason": plan.stop_reason, "stop_sequence": None},
                                   "usage": {"output_tokens": out_tokens}})
    yield _frame("message_stop", {"type": "message_stop"})


# --------------------------------------------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------------------------------------------
def _authed(request: Request) -> bool:
    auth = request.headers.get("authorization", "")
    return auth.lower().startswith("bearer ") and len(auth) > 7 or bool(request.headers.get("x-api-key"))


def _error(status: int, err_type: str, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"type": "error", "error": {"type": err_type, "message": message}}, status_code=status,
                        headers=headers or {})


@router.get("/v1/models")
async def list_models():
    # Deliberately unauthenticated: the compose healthcheck and the backend's IliadAnthropicProvider.healthcheck()
    # both probe this URL, and a 401 would keep the container "unhealthy". /v1/messages stays strict.
    return {"data": [{"id": m, "type": "model", "display_name": m} for m in MODELS], "has_more": False,
            "first_id": MODELS[0], "last_id": MODELS[-1]}


@router.post("/v1/messages")
async def create_message(request: Request):
    if not _authed(request):
        return _error(401, "authentication_error", "missing Authorization bearer token or x-api-key header")
    try:
        body = await request.json()
    except Exception:
        return _error(400, "invalid_request_error", "body must be JSON")
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list) or not body["messages"]:
        return _error(400, "invalid_request_error", "messages: field required")
    if not body.get("model"):
        return _error(400, "invalid_request_error", "model: field required")

    plan = plan_response(body)
    model = body["model"]
    stream = bool(body.get("stream"))
    print(f"[mock-iliad] messages model={model} stream={stream} scenario={plan.scenario} "
          f"tools={len(body.get('tools') or [])} beta={request.headers.get('anthropic-beta', '-')}", flush=True)
    if plan.http_error:
        status, payload, headers = plan.http_error
        return JSONResponse(payload, status_code=status, headers=headers)

    msg_id = f"msg_mock_{next(_msg_counter):06d}"
    input_tokens = _approx_input_tokens(body)
    if stream:
        return StreamingResponse(_stream(msg_id, model, plan, input_tokens), media_type="text/event-stream",
                                 headers={"cache-control": "no-cache", "x-request-id": msg_id})
    return JSONResponse({
        "id": msg_id, "type": "message", "role": "assistant", "model": model, "content": plan.blocks,
        "stop_reason": plan.stop_reason, "stop_sequence": None,
        "usage": _usage(input_tokens, _output_tokens(plan.blocks)),
    }, headers={"x-request-id": msg_id})
