"""Mock OIDC provider (PingID / PingOne stand-in). Issuer: <base>/oidc

  GET  /oidc/.well-known/openid-configuration   discovery
  GET  /oidc/jwks                               JWKS with one RSA key (kid "mock-1") generated at startup
  GET  /oidc/authorize                          login form (email + comma-separated groups); `auto=1&email=..&groups=..`
                                                submits immediately. Supports state, nonce, PKCE S256.
  POST /oidc/authorize/login                    form target -> redirect to redirect_uri?code=..&state=..
  POST /oidc/token                              authorization_code (+PKCE) and refresh_token grants ->
                                                id_token (RS256), access_token (opaque), refresh_token, expires_in
  POST /oidc/introspect                         RFC 7662: {active, sub, email, groups, ...}
  GET  /oidc/userinfo                           bearer access_token -> claims
  GET  /oidc/logout                             end_session: redirect to post_logout_redirect_uri
"""
from __future__ import annotations

import html
from typing import Any
from urllib.parse import urlencode, urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from jose import jwt

from common import BASE_URL, b64url_uint, hidden_fields, now, opaque_token, page, pkce_ok

router = APIRouter(prefix="/oidc", tags=["oidc"])

ISSUER = f"{BASE_URL}/oidc"
KID = "mock-1"
CODE_TTL = 300
TOKEN_TTL = 3600
DEFAULT_GROUPS = "cw-org-admins"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_PEM = _private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()).decode()
_pub = _private_key.public_key().public_numbers()
JWKS = {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": KID, "n": b64url_uint(_pub.n), "e": b64url_uint(_pub.e)}]}

pending: dict[str, dict[str, Any]] = {}
codes: dict[str, dict[str, Any]] = {}
access_tokens: dict[str, dict[str, Any]] = {}
refresh_tokens: dict[str, dict[str, Any]] = {}


def reset() -> None:
    for d in (pending, codes, access_tokens, refresh_tokens):
        d.clear()


def _groups(raw: str | None) -> list[str]:
    return [g.strip() for g in (raw if raw is not None else DEFAULT_GROUPS).split(",") if g.strip()]


def _name(email: str) -> str:
    local = email.split("@", 1)[0]
    return " ".join(p.capitalize() for p in local.replace(".", " ").replace("_", " ").split()) or email


# --------------------------------------------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------------------------------------------
@router.get("/.well-known/openid-configuration")
async def discovery():
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "jwks_uri": f"{ISSUER}/jwks",
        "userinfo_endpoint": f"{ISSUER}/userinfo",
        "end_session_endpoint": f"{ISSUER}/logout",
        "introspection_endpoint": f"{ISSUER}/introspect",
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": ["openid", "profile", "email", "groups", "offline_access"],
        "claims_supported": ["iss", "sub", "aud", "exp", "iat", "nonce", "email", "email_verified", "name", "groups"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_basic", "client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
    }


@router.get("/jwks")
async def jwks():
    return JWKS


# --------------------------------------------------------------------------------------------------------------
# authorization + login form
# --------------------------------------------------------------------------------------------------------------
def _redirect_with(uri: str, params: dict[str, str | None]) -> RedirectResponse:
    q = urlencode({k: v for k, v in params.items() if v is not None})
    return RedirectResponse(f"{uri}{'&' if '?' in uri else '?'}{q}", status_code=302)


def _issue_code(req: dict[str, Any], email: str, groups: list[str]) -> RedirectResponse:
    code = opaque_token("oidc_code_")
    codes[code] = {**req, "email": email.strip().lower(), "groups": groups, "auth_time": now(), "expires_at": now() + CODE_TTL}
    print(f"[mock-oidc] login email={email} groups={groups} client={req['client_id']}", flush=True)
    return _redirect_with(req["redirect_uri"], {"code": code, "state": req.get("state")})


@router.get("/authorize")
async def authorize(request: Request):
    q = request.query_params
    client_id, redirect_uri = q.get("client_id"), q.get("redirect_uri")
    if not client_id:
        return JSONResponse({"error": "invalid_request", "error_description": "client_id required"}, status_code=400)
    if not redirect_uri or not urlparse(redirect_uri).scheme:
        return JSONResponse({"error": "invalid_request", "error_description": "redirect_uri must be an absolute URI"}, status_code=400)
    state = q.get("state")
    if q.get("response_type") != "code":
        return _redirect_with(redirect_uri, {"error": "unsupported_response_type", "state": state})
    if q.get("code_challenge") and q.get("code_challenge_method", "S256") != "S256":
        return _redirect_with(redirect_uri, {"error": "invalid_request", "error_description": "only S256 is supported",
                                             "state": state})
    req = {"client_id": client_id, "redirect_uri": redirect_uri, "state": state, "nonce": q.get("nonce"),
           "scope": q.get("scope") or "openid", "code_challenge": q.get("code_challenge")}
    if q.get("auto") == "1":  # test shortcut: log in without the form
        return _issue_code(req, q.get("email") or "admin@example.com", _groups(q.get("groups")))
    req_id = opaque_token("req_")
    pending[req_id] = req
    body = (f"<p>Sign in to <b>{html.escape(client_id)}</b> (mock PingID).</p>"
            f"<form method='post' action='/oidc/authorize/login'>{hidden_fields({'req_id': req_id})}"
            "<label>Email</label><input name='email' type='email' value='admin@example.com' required>"
            f"<label>Groups (comma separated)</label><input name='groups' value='{DEFAULT_GROUPS}'>"
            "<button type='submit'>Sign in</button></form>")
    return page("Mock PingID - sign in", body)


@router.post("/authorize/login")
async def login(req_id: str = Form(...), email: str = Form(...), groups: str = Form(DEFAULT_GROUPS)):
    req = pending.pop(req_id, None)
    if req is None:
        return JSONResponse({"error": "invalid_request", "error_description": "unknown or already used req_id"}, status_code=400)
    return _issue_code(req, email, _groups(groups))


# --------------------------------------------------------------------------------------------------------------
# tokens
# --------------------------------------------------------------------------------------------------------------
def _token_error(error: str, description: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": error, "error_description": description}, status_code=status, headers={"cache-control": "no-store"})


def _client_id_from(request: Request, form) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        import base64
        try:
            return base64.b64decode(auth[6:]).decode().split(":", 1)[0]
        except Exception:
            return None
    return form.get("client_id")


def _mint(rec: dict[str, Any]) -> dict[str, Any]:
    iat = now()
    email = rec["email"]
    claims = {"iss": ISSUER, "sub": f"mock|{email}", "aud": rec["client_id"], "iat": iat, "exp": iat + TOKEN_TTL,
              "auth_time": rec.get("auth_time", iat), "email": email, "email_verified": True, "name": _name(email),
              "groups": rec["groups"]}
    if rec.get("nonce"):
        claims["nonce"] = rec["nonce"]
    id_token = jwt.encode(claims, PRIVATE_PEM, algorithm="RS256", headers={"kid": KID})
    access, refresh = opaque_token("oidc_at_"), opaque_token("oidc_rt_")
    base = {k: rec[k] for k in ("client_id", "email", "groups", "scope", "auth_time")}
    access_tokens[access] = {**base, "sub": claims["sub"], "iat": iat, "expires_at": iat + TOKEN_TTL}
    refresh_tokens[refresh] = {**base, "nonce": None, "access_token": access}
    return {"access_token": access, "token_type": "Bearer", "expires_in": TOKEN_TTL, "refresh_token": refresh,
            "id_token": id_token, "scope": rec["scope"]}


@router.post("/token")
async def token(request: Request):
    form = await request.form()
    grant = form.get("grant_type")
    client_id = _client_id_from(request, form)
    if not client_id:
        return _token_error("invalid_client", "client_id required (form field or basic auth)", 401)
    if grant == "authorization_code":
        rec = codes.pop(form.get("code") or "", None)
        if rec is None or rec["expires_at"] <= now():
            return _token_error("invalid_grant", "unknown, used or expired code")
        if rec["client_id"] != client_id:
            return _token_error("invalid_grant", "code was issued to a different client")
        if rec["redirect_uri"] != form.get("redirect_uri"):
            return _token_error("invalid_grant", "redirect_uri mismatch")
        if rec.get("code_challenge") and not pkce_ok(form.get("code_verifier"), rec["code_challenge"]):
            return _token_error("invalid_grant", "PKCE code_verifier does not match code_challenge")
        resp = _mint(rec)
    elif grant == "refresh_token":
        rec = refresh_tokens.pop(form.get("refresh_token") or "", None)
        if rec is None:
            return _token_error("invalid_grant", "unknown or already rotated refresh_token")
        if rec["client_id"] != client_id:
            return _token_error("invalid_grant", "refresh_token was issued to a different client")
        access_tokens.pop(rec["access_token"], None)
        resp = _mint(rec)
    else:
        return _token_error("unsupported_grant_type", f"grant_type {grant!r} not supported")
    return JSONResponse(resp, headers={"cache-control": "no-store", "pragma": "no-cache"})


@router.post("/introspect")
async def introspect(token: str = Form(...)):
    rec = access_tokens.get(token)
    if rec is None or rec["expires_at"] <= now():
        return {"active": False}
    return {"active": True, "sub": rec["sub"], "email": rec["email"], "groups": rec["groups"], "client_id": rec["client_id"],
            "scope": rec["scope"], "token_type": "Bearer", "iat": rec["iat"], "exp": rec["expires_at"], "iss": ISSUER}


@router.get("/userinfo")
async def userinfo(request: Request):
    auth = request.headers.get("authorization", "")
    rec = access_tokens.get(auth[7:].strip()) if auth.lower().startswith("bearer ") else None
    if rec is None or rec["expires_at"] <= now():
        return JSONResponse({"error": "invalid_token"}, status_code=401, headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})
    return {"sub": rec["sub"], "email": rec["email"], "email_verified": True, "name": _name(rec["email"]), "groups": rec["groups"]}


@router.get("/logout")
async def logout(post_logout_redirect_uri: str | None = None, state: str | None = None, id_token_hint: str | None = None,
                 client_id: str | None = None):
    print(f"[mock-oidc] logout client={client_id}", flush=True)
    if post_logout_redirect_uri:
        return _redirect_with(post_logout_redirect_uri, {"state": state})
    return PlainTextResponse("Signed out of mock PingID.")
