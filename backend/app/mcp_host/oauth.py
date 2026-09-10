"""OAuth 2.1 + PKCE client for remote MCP connectors, run server-side by the backbone.

Implements: RFC 9728 protected-resource metadata discovery -> AS metadata (RFC 8414), RFC 7591 dynamic client
registration when the AS supports it and no client_id is configured, Authorization Code + PKCE (S256),
RFC 8707 `resource` audience binding, refresh-token rotation. Tokens are stored envelope-encrypted and
injected as `Authorization: Bearer` into the MCP server config at run start.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx


@dataclass
class ASMetadata:
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str | None = None
    issuer: str | None = None
    code_challenge_methods: list[str] | None = None


def make_pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


async def discover(mcp_url: str, oauth_cfg: dict[str, Any] | None, client: httpx.AsyncClient | None = None) -> ASMetadata:
    """Prefer explicit endpoints from the catalog row; else RFC 9728 -> RFC 8414 discovery."""
    oauth_cfg = oauth_cfg or {}
    if oauth_cfg.get("authorization_endpoint") and oauth_cfg.get("token_endpoint"):
        return ASMetadata(oauth_cfg["authorization_endpoint"], oauth_cfg["token_endpoint"],
                          oauth_cfg.get("registration_endpoint"), oauth_cfg.get("issuer"))
    own = client is None
    client = client or httpx.AsyncClient(timeout=10)
    try:
        u = urlparse(mcp_url)
        origin = f"{u.scheme}://{u.netloc}"
        issuer = None
        for path in (f"/.well-known/oauth-protected-resource{u.path}", "/.well-known/oauth-protected-resource"):
            r = await client.get(origin + path)
            if r.status_code == 200:
                servers = r.json().get("authorization_servers") or []
                if servers:
                    issuer = servers[0]
                    break
        issuer = issuer or oauth_cfg.get("issuer") or origin
        iu = urlparse(issuer)
        for path in (f"/.well-known/oauth-authorization-server{iu.path}", "/.well-known/oauth-authorization-server",
                     f"{iu.path}/.well-known/openid-configuration", "/.well-known/openid-configuration"):
            r = await client.get(f"{iu.scheme}://{iu.netloc}{path}")
            if r.status_code == 200:
                m = r.json()
                return ASMetadata(m["authorization_endpoint"], m["token_endpoint"], m.get("registration_endpoint"),
                                  m.get("issuer", issuer), m.get("code_challenge_methods_supported"))
        raise RuntimeError(f"no authorization server metadata found for {mcp_url}")
    finally:
        if own:
            await client.aclose()


async def register_client(meta: ASMetadata, redirect_uri: str, client_name: str, client: httpx.AsyncClient | None = None) -> str:
    if not meta.registration_endpoint:
        raise RuntimeError("authorization server does not support dynamic client registration")
    own = client is None
    client = client or httpx.AsyncClient(timeout=10)
    try:
        r = await client.post(meta.registration_endpoint, json={
            "client_name": client_name, "redirect_uris": [redirect_uri], "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"], "token_endpoint_auth_method": "none"})
        r.raise_for_status()
        return r.json()["client_id"]
    finally:
        if own:
            await client.aclose()


def build_authorize_url(meta: ASMetadata, *, client_id: str, redirect_uri: str, scopes: list[str], state: str,
                        code_challenge: str, resource: str | None) -> str:
    q = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "state": state,
         "code_challenge": code_challenge, "code_challenge_method": "S256"}
    if scopes:
        q["scope"] = " ".join(scopes)
    if resource:
        q["resource"] = resource
    return f"{meta.authorization_endpoint}{'&' if '?' in meta.authorization_endpoint else '?'}{urlencode(q)}"


async def exchange_code(meta: ASMetadata, *, code: str, client_id: str, client_secret: str | None, redirect_uri: str,
                        code_verifier: str, resource: str | None, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "client_id": client_id,
            "code_verifier": code_verifier}
    if resource:
        data["resource"] = resource
    if client_secret:
        data["client_secret"] = client_secret
    own = client is None
    client = client or httpx.AsyncClient(timeout=10)
    try:
        r = await client.post(meta.token_endpoint, data=data, headers={"Accept": "application/json"})
        r.raise_for_status()
        return r.json()
    finally:
        if own:
            await client.aclose()


async def refresh(meta: ASMetadata, *, refresh_token: str, client_id: str, client_secret: str | None, resource: str | None,
                  client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id}
    if resource:
        data["resource"] = resource
    if client_secret:
        data["client_secret"] = client_secret
    own = client is None
    client = client or httpx.AsyncClient(timeout=10)
    try:
        r = await client.post(meta.token_endpoint, data=data, headers={"Accept": "application/json"})
        r.raise_for_status()
        return r.json()
    finally:
        if own:
            await client.aclose()
