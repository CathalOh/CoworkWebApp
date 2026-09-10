"""Single-port mock backbone dependencies for local dev + e2e tests. Run: `uvicorn server:app --port 9100`.

  /v1/*                       mock ILIAD (Anthropic Messages API)          -> anthropic_api.py
  /mcp                        mock remote MCP server "mock-drive" (OAuth)  -> mcp_server.py
  /.well-known/*, /oauth/*    OAuth 2.1 authorization server for /mcp      -> oauth_as.py
  /oidc/*                     mock OIDC provider (PingID stand-in)          -> oidc.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # flat modules; works from any cwd

from fastapi import FastAPI, Request  # noqa: E402

import anthropic_api  # noqa: E402
import mcp_server  # noqa: E402
import oauth_as  # noqa: E402
import oidc  # noqa: E402
from common import BASE_URL  # noqa: E402

app = FastAPI(title="mock-iliad", version="0.1.0", docs_url="/docs")


@app.middleware("http")
async def log_request_line(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - started) * 1000
    print(f'{request.client.host if request.client else "-"} "{request.method} {request.url.path}'
          f'{"?" + request.url.query if request.url.query else ""}" {response.status_code} {ms:.1f}ms', flush=True)
    return response


@app.get("/", include_in_schema=False)
async def index():
    return {
        "service": "mock-iliad", "base_url": BASE_URL,
        "anthropic": ["/v1/models", "/v1/messages"],
        "mcp": ["/mcp"],
        "oauth": ["/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp",
                  "/.well-known/oauth-authorization-server", "/oauth/register", "/oauth/authorize",
                  "/oauth/authorize/decision", "/oauth/token"],
        "oidc": ["/oidc/.well-known/openid-configuration", "/oidc/jwks", "/oidc/authorize", "/oidc/authorize/login",
                 "/oidc/token", "/oidc/introspect", "/oidc/userinfo", "/oidc/logout"],
    }


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True}


app.include_router(anthropic_api.router)
app.include_router(mcp_server.router)
app.include_router(oauth_as.router)
app.include_router(oidc.router)
