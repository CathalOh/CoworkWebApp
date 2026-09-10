"""PingID OIDC (PingOne / PingFederate) — backend-for-frontend pattern.

The SPA never holds tokens: the backend starts Authorization Code + PKCE, exchanges the code, validates the
ID token (JWKS from discovery; introspection if Ping issues opaque access tokens), maps group claims to app
roles, and issues an HttpOnly session cookie. Logout is RP-initiated via the end_session endpoint.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from jose import jwt

from app.config import get_settings

_discovery_cache: dict[str, Any] = {}
_jwks_cache: dict[str, Any] = {"keys": None, "fetched": 0.0}


async def discovery() -> dict[str, Any]:
    s = get_settings()
    if not s.oidc_issuer:
        raise RuntimeError("OIDC_ISSUER not configured")
    if _discovery_cache.get("issuer") == s.oidc_issuer:
        return _discovery_cache["doc"]
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(s.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration")
        r.raise_for_status()
        doc = r.json()
    _discovery_cache.update(issuer=s.oidc_issuer, doc=doc)
    return doc


async def jwks(force: bool = False) -> dict[str, Any]:
    if not force and _jwks_cache["keys"] and time.time() - _jwks_cache["fetched"] < 3600:
        return _jwks_cache["keys"]
    doc = await discovery()
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(doc["jwks_uri"])
        r.raise_for_status()
        _jwks_cache.update(keys=r.json(), fetched=time.time())
    return _jwks_cache["keys"]


def make_pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


async def authorize_url(state: str, nonce: str, code_challenge: str) -> str:
    s = get_settings()
    doc = await discovery()
    q = {"response_type": "code", "client_id": s.oidc_client_id, "redirect_uri": s.oidc_redirect_uri, "scope": s.oidc_scopes,
         "state": state, "nonce": nonce, "code_challenge": code_challenge, "code_challenge_method": "S256"}
    return f"{doc['authorization_endpoint']}?{urlencode(q)}"


async def exchange_code(code: str, code_verifier: str) -> dict[str, Any]:
    s = get_settings()
    doc = await discovery()
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": s.oidc_redirect_uri, "client_id": s.oidc_client_id,
            "code_verifier": code_verifier}
    auth = (s.oidc_client_id, s.oidc_client_secret) if s.oidc_client_secret else None
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(doc["token_endpoint"], data=data, auth=auth)
        r.raise_for_status()
        return r.json()


async def validate_id_token(id_token: str, nonce: str) -> dict[str, Any]:
    s = get_settings()
    keys = await jwks()
    header = jwt.get_unverified_header(id_token)
    key = next((k for k in keys.get("keys", []) if k.get("kid") == header.get("kid")), None)
    if key is None:  # key rotation: refresh the truststore once
        keys = await jwks(force=True)
        key = next((k for k in keys.get("keys", []) if k.get("kid") == header.get("kid")), None)
    if key is None:
        raise ValueError("unknown signing key")
    claims = jwt.decode(id_token, key, algorithms=[header.get("alg", "RS256")], audience=s.oidc_client_id, issuer=s.oidc_issuer)
    if claims.get("nonce") != nonce:
        raise ValueError("nonce mismatch")
    return claims


async def introspect(access_token: str) -> dict[str, Any]:
    """For opaque access tokens (RFC 7662)."""
    s = get_settings()
    ep = s.oidc_introspection_endpoint or (await discovery()).get("introspection_endpoint")
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(ep, data={"token": access_token}, auth=(s.oidc_client_id or "", s.oidc_client_secret or ""))
        r.raise_for_status()
        return r.json()


async def end_session_url(id_token_hint: str | None, post_logout_redirect: str) -> str | None:
    try:
        doc = await discovery()
    except Exception:
        return None
    ep = doc.get("end_session_endpoint")
    if not ep:
        return None
    q = {"post_logout_redirect_uri": post_logout_redirect, "client_id": get_settings().oidc_client_id}
    if id_token_hint:
        q["id_token_hint"] = id_token_hint
    return f"{ep}?{urlencode(q)}"


def roles_from_claims(claims: dict[str, Any]) -> set[str]:
    s = get_settings()
    mapping = json.loads(s.role_group_map_json)
    groups = claims.get(s.oidc_groups_claim) or claims.get("realm_access", {}).get("roles") or []
    if isinstance(groups, str):
        groups = [groups]
    roles = {mapping[g] for g in groups if g in mapping}
    return roles | {"user"}
