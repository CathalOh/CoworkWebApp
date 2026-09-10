"""OAuth 2.1 authorization server protecting the mock MCP server (`/mcp`).

  GET  /.well-known/oauth-protected-resource[/mcp]  RFC 9728 protected-resource metadata
  GET  /.well-known/oauth-authorization-server      RFC 8414 AS metadata
  POST /oauth/register                              RFC 7591 dynamic client registration (public clients)
  GET  /oauth/authorize                             consent page (Approve form / Deny link); `auto_approve=1` skips it
  GET|POST /oauth/authorize/decision                consent decision -> redirect with code+state or error=access_denied
  POST /oauth/token                                 authorization_code (PKCE S256, redirect_uri, RFC 8707 resource) and
                                                    refresh_token (rotating) grants

Everything lives in memory. The backend's seeded connector uses the pre-registered client `cowork-backbone`,
which may use any redirect_uri; dynamically registered clients are pinned to their registered redirect_uris.
"""
from __future__ import annotations

import html
import secrets
from typing import Any
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

from common import BASE_URL, hidden_fields, now, opaque_token, page, pkce_ok

router = APIRouter(tags=["oauth"])

RESOURCE = f"{BASE_URL}/mcp"
CODE_TTL = 300
ACCESS_TTL = 3600
SCOPES_SUPPORTED = ["drive.read", "drive.write"]

# client_id -> {"client_name", "redirect_uris": [] (empty = any)}
clients: dict[str, dict[str, Any]] = {
    "cowork-backbone": {"client_name": "Cowork backbone (pre-registered)", "redirect_uris": []},
}
pending: dict[str, dict[str, Any]] = {}  # consent-page requests awaiting a decision
codes: dict[str, dict[str, Any]] = {}  # auth code -> binding
access_tokens: dict[str, dict[str, Any]] = {}
refresh_tokens: dict[str, dict[str, Any]] = {}


def reset() -> None:
    for d in (pending, codes, access_tokens, refresh_tokens):
        d.clear()
    clients.clear()
    clients["cowork-backbone"] = {"client_name": "Cowork backbone (pre-registered)", "redirect_uris": []}


def validate_access_token(token: str | None) -> dict[str, Any] | None:
    """Used by the MCP server. Returns the token record or None when unknown/expired."""
    rec = access_tokens.get(token or "")
    if not rec or rec["expires_at"] <= now():
        return None
    return rec


# --------------------------------------------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------------------------------------------
def _resource_metadata() -> dict[str, Any]:
    return {"resource": RESOURCE, "authorization_servers": [BASE_URL], "scopes_supported": SCOPES_SUPPORTED,
            "bearer_methods_supported": ["header"], "resource_name": "mock-drive"}


@router.get("/.well-known/oauth-protected-resource/mcp")
async def protected_resource_mcp():
    return _resource_metadata()


@router.get("/.well-known/oauth-protected-resource")
async def protected_resource():
    return _resource_metadata()


@router.get("/.well-known/oauth-authorization-server")
async def as_metadata():
    return {
        "issuer": BASE_URL,
        "authorization_endpoint": f"{BASE_URL}/oauth/authorize",
        "token_endpoint": f"{BASE_URL}/oauth/token",
        "registration_endpoint": f"{BASE_URL}/oauth/register",
        "scopes_supported": SCOPES_SUPPORTED,
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
    }


# --------------------------------------------------------------------------------------------------------------
# dynamic client registration
# --------------------------------------------------------------------------------------------------------------
@router.post("/oauth/register", status_code=201)
async def register(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_client_metadata", "error_description": "body must be JSON"}, status_code=400)
    redirect_uris = body.get("redirect_uris") or []
    if not isinstance(redirect_uris, list) or not all(isinstance(u, str) and urlparse(u).scheme for u in redirect_uris):
        return JSONResponse({"error": "invalid_redirect_uri", "error_description": "redirect_uris must be absolute URIs"},
                            status_code=400)
    client_id = f"mock-client-{secrets.token_hex(6)}"
    clients[client_id] = {"client_name": body.get("client_name") or client_id, "redirect_uris": redirect_uris}
    return {
        "client_id": client_id, "client_id_issued_at": now(), "client_name": clients[client_id]["client_name"],
        "redirect_uris": redirect_uris, "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"], "token_endpoint_auth_method": "none",
    }


# --------------------------------------------------------------------------------------------------------------
# authorization endpoint + consent
# --------------------------------------------------------------------------------------------------------------
def _redirect_with(uri: str, params: dict[str, str | None]) -> RedirectResponse:
    q = urlencode({k: v for k, v in params.items() if v is not None})
    return RedirectResponse(f"{uri}{'&' if '?' in uri else '?'}{q}", status_code=302)


def _issue_code(req: dict[str, Any]) -> RedirectResponse:
    code = opaque_token("code_")
    codes[code] = {**req, "expires_at": now() + CODE_TTL}
    return _redirect_with(req["redirect_uri"], {"code": code, "state": req.get("state")})


@router.get("/oauth/authorize")
async def authorize(request: Request):
    q = request.query_params
    client_id, redirect_uri = q.get("client_id"), q.get("redirect_uri")
    client = clients.get(client_id or "")
    if client is None:
        return JSONResponse({"error": "invalid_client", "error_description": "unknown client_id"}, status_code=400)
    if not redirect_uri or not urlparse(redirect_uri).scheme or (client["redirect_uris"] and redirect_uri not in client["redirect_uris"]):
        return JSONResponse({"error": "invalid_request", "error_description": "redirect_uri missing or not registered"},
                            status_code=400)
    state = q.get("state")
    if q.get("response_type") != "code":
        return _redirect_with(redirect_uri, {"error": "unsupported_response_type", "state": state})
    if not q.get("code_challenge") or q.get("code_challenge_method", "S256") != "S256":
        return _redirect_with(redirect_uri, {"error": "invalid_request", "error_description": "PKCE S256 code_challenge required",
                                             "state": state})
    req = {"client_id": client_id, "redirect_uri": redirect_uri, "state": state, "code_challenge": q["code_challenge"],
           "scope": q.get("scope") or "", "resource": q.get("resource")}
    if q.get("auto_approve") == "1":  # test shortcut: skip the consent page
        return _issue_code(req)
    req_id = opaque_token("req_")
    pending[req_id] = req
    scopes = " ".join(f"<code>{html.escape(s)}</code>" for s in req["scope"].split()) or "<em>(none)</em>"
    body = (f"<p><b>{html.escape(client['client_name'])}</b> (<code>{html.escape(client_id)}</code>) wants access to "
            f"<code>{html.escape(req['resource'] or RESOURCE)}</code> with scopes {scopes}.</p>"
            f"<form method='post' action='/oauth/authorize/decision'>{hidden_fields({'req_id': req_id, 'decision': 'approve'})}"
            "<button type='submit'>Approve</button></form>"
            f"<p><a href='/oauth/authorize/decision?req_id={req_id}&decision=deny'>Deny</a></p>")
    return page("Mock Drive - authorize", body)


def _decide(req_id: str | None, decision: str | None):
    req = pending.pop(req_id or "", None)
    if req is None:
        return JSONResponse({"error": "invalid_request", "error_description": "unknown or already used req_id"}, status_code=400)
    if decision != "approve":
        return _redirect_with(req["redirect_uri"], {"error": "access_denied", "state": req.get("state")})
    return _issue_code(req)


@router.post("/oauth/authorize/decision")
async def decision_post(req_id: str = Form(...), decision: str = Form("deny")):
    return _decide(req_id, decision)


@router.get("/oauth/authorize/decision")
async def decision_get(req_id: str, decision: str = "deny"):
    return _decide(req_id, decision)


# --------------------------------------------------------------------------------------------------------------
# token endpoint
# --------------------------------------------------------------------------------------------------------------
def _token_error(error: str, description: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": error, "error_description": description}, status_code=status,
                        headers={"cache-control": "no-store"})


def _mint(client_id: str, scope: str, resource: str | None) -> dict[str, Any]:
    access, refresh = opaque_token("at_"), opaque_token("rt_")
    access_tokens[access] = {"client_id": client_id, "scope": scope, "resource": resource, "expires_at": now() + ACCESS_TTL}
    refresh_tokens[refresh] = {"client_id": client_id, "scope": scope, "resource": resource, "access_token": access}
    return {"access_token": access, "token_type": "Bearer", "expires_in": ACCESS_TTL, "refresh_token": refresh, "scope": scope}


@router.post("/oauth/token")
async def token(request: Request):
    form = await request.form()
    grant = form.get("grant_type")
    client_id = form.get("client_id")
    if client_id not in clients:
        return _token_error("invalid_client", "unknown client_id", 401)
    resource = form.get("resource")

    if grant == "authorization_code":
        rec = codes.pop(form.get("code") or "", None)
        if rec is None or rec["expires_at"] <= now():
            return _token_error("invalid_grant", "unknown, used or expired code")
        if rec["client_id"] != client_id:
            return _token_error("invalid_grant", "code was issued to a different client")
        if rec["redirect_uri"] != form.get("redirect_uri"):
            return _token_error("invalid_grant", "redirect_uri mismatch")
        if not pkce_ok(form.get("code_verifier"), rec["code_challenge"]):
            return _token_error("invalid_grant", "PKCE code_verifier does not match code_challenge")
        if resource and rec.get("resource") and resource != rec["resource"]:
            return _token_error("invalid_target", "resource does not match the authorization request")
        resp = _mint(client_id, rec["scope"], rec.get("resource") or resource)
    elif grant == "refresh_token":
        rec = refresh_tokens.pop(form.get("refresh_token") or "", None)
        if rec is None:
            return _token_error("invalid_grant", "unknown or already rotated refresh_token")
        if rec["client_id"] != client_id:
            return _token_error("invalid_grant", "refresh_token was issued to a different client")
        if resource and rec.get("resource") and resource != rec["resource"]:
            return _token_error("invalid_target", "resource does not match the original grant")
        access_tokens.pop(rec["access_token"], None)  # rotation: old access token dies with the old refresh token
        resp = _mint(client_id, rec["scope"], rec.get("resource"))
    else:
        return _token_error("unsupported_grant_type", f"grant_type {grant!r} not supported")
    print(f"[mock-oauth] {grant} client={client_id} scope={resp['scope']!r}", flush=True)
    return JSONResponse(resp, headers={"cache-control": "no-store", "pragma": "no-cache"})
