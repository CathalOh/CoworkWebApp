"""Mock remote MCP server "mock-drive": streamable HTTP transport, JSON-RPC 2.0 over POST /mcp.

Protected by the OAuth AS in `oauth_as.py`: a missing/invalid bearer token yields 401 with
`WWW-Authenticate: Bearer resource_metadata="<base>/.well-known/oauth-protected-resource/mcp"` so a compliant client
can discover the authorization server (RFC 9728). Responses are plain application/json (allowed by the streamable
HTTP spec; no SSE upgrade). GET /mcp -> 405 (no server-initiated stream).

Methods: initialize, notifications/initialized (202), ping, tools/list, tools/call (list_files, read_file).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from common import BASE_URL, opaque_token
from oauth_as import validate_access_token

router = APIRouter(tags=["mcp"])

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "mock-drive", "version": "0.1.0"}
FILES = ["metrics.xlsx", "narrative.docx"]

TOOLS = [
    {"name": "list_files", "description": "List the files in the mock drive.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "read_file", "description": "Read a file from the mock drive.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "description": "File path"}},
                     "required": ["path"], "additionalProperties": False}},
]


def _rpc_result(id_: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _rpc_error(id_: Any, code: int, message: str, status: int = 200) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}, status_code=status)


def _unauthorized(description: str) -> JSONResponse:
    www = (f'Bearer resource_metadata="{BASE_URL}/.well-known/oauth-protected-resource/mcp", '
           f'error="invalid_token", error_description="{description}"')
    return JSONResponse({"error": "invalid_token", "error_description": description}, status_code=401,
                        headers={"WWW-Authenticate": www})


def _call_tool(name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    if name == "list_files":
        return {"content": [{"type": "text", "text": "\n".join(FILES)}], "isError": False,
                "structuredContent": {"files": FILES}}
    if name == "read_file":
        path = args.get("path")
        if not isinstance(path, str) or not path:
            return {"content": [{"type": "text", "text": "read_file: 'path' (string) is required"}], "isError": True}
        return {"content": [{"type": "text", "text": f"contents of {path}"}], "isError": False}
    return None


@router.get("/mcp")
async def mcp_get():
    return JSONResponse({"error": "method not allowed", "detail": "this server does not open server-initiated streams"},
                        status_code=405, headers={"Allow": "POST, DELETE"})


@router.delete("/mcp")
async def mcp_delete():
    return Response(status_code=204)


@router.post("/mcp")
async def mcp_post(request: Request):
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else None
    if token is None:
        return _unauthorized("bearer token required")
    if validate_access_token(token) is None:
        return _unauthorized("token unknown or expired")

    try:
        msg = await request.json()
    except Exception:
        return _rpc_error(None, -32700, "parse error", status=400)
    if isinstance(msg, list):  # batches were removed in 2025-06-18
        return _rpc_error(None, -32600, "batch requests are not supported", status=400)
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return _rpc_error(None, -32600, "invalid JSON-RPC request", status=400)

    method, params, id_ = msg["method"], msg.get("params") or {}, msg.get("id")
    print(f"[mock-mcp] {method} id={id_}", flush=True)

    if "id" not in msg:  # notification
        return Response(status_code=202)

    if method == "initialize":
        return JSONResponse(_rpc_result(id_, {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}},
                                              "serverInfo": SERVER_INFO,
                                              "instructions": "Mock Drive: list_files, then read_file(path)."}),
                            headers={"Mcp-Session-Id": opaque_token("mcp_")})
    if method == "ping":
        return _rpc_result(id_, {})
    if method == "tools/list":
        return _rpc_result(id_, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        result = _call_tool(name or "", args if isinstance(args, dict) else {})
        if result is None:
            return _rpc_error(id_, -32602, f"unknown tool: {name!r}")
        return _rpc_result(id_, result)
    return _rpc_error(id_, -32601, f"method not found: {method}")
