"""MCP host: turns catalog rows + per-user credentials into McpServerConfig dicts for the runtime,
and tracks connection status for the UI."""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp_host import oauth
from app.models import Connector, ConnectorCredential, User
from app.models.base import utcnow
from app.security.crypto import Envelope, decrypt, encrypt


def connector_visible_to(c: Connector, user: User) -> bool:
    if not c.approved or not c.enabled:
        return False
    if not c.team_ids:
        return True
    return bool({uuid.UUID(t) if isinstance(t, str) else t for t in c.team_ids} & user.team_ids)


async def store_token(db: AsyncSession, user_id: uuid.UUID, connector_id: uuid.UUID, token_resp: dict[str, Any]) -> ConnectorCredential:
    """Both tokens are encrypted under one fresh DEK so a single enc_dek unwraps either."""
    aad = f"{user_id}:{connector_id}".encode()
    rt = token_resp.get("refresh_token")
    payload = token_resp["access_token"].encode() + b"\x00" + (rt or "").encode()
    env = encrypt(payload, aad)
    expires_at = utcnow() + timedelta(seconds=int(token_resp["expires_in"])) if token_resp.get("expires_in") else None
    cred = (await db.execute(select(ConnectorCredential).where(ConnectorCredential.user_id == user_id,
                                                                 ConnectorCredential.connector_id == connector_id))).scalar_one_or_none()
    if cred is None:
        cred = ConnectorCredential(user_id=user_id, connector_id=connector_id, enc_token=b"", enc_dek=b"")
        db.add(cred)
    cred.enc_token, cred.enc_dek, cred.key_version = env.ciphertext, env.enc_dek, env.key_version
    cred.enc_refresh_token = b"1" if rt else None
    cred.token_type = token_resp.get("token_type", "Bearer")
    scope = token_resp.get("scope")
    cred.scopes = scope.split() if isinstance(scope, str) and scope else None
    cred.expires_at = expires_at
    cred.status = "connected"
    await db.flush()
    return cred


def decrypt_tokens(cred: ConnectorCredential) -> tuple[str, str | None]:
    aad = f"{cred.user_id}:{cred.connector_id}".encode()
    raw = decrypt(Envelope(ciphertext=cred.enc_token, enc_dek=cred.enc_dek, key_version=cred.key_version), aad)
    access, _, refresh_tok = raw.partition(b"\x00")
    return access.decode(), (refresh_tok.decode() or None)


async def access_token_for(db: AsyncSession, cred: ConnectorCredential, connector: Connector) -> str | None:
    """Return a live access token, refreshing if expired and a refresh token exists."""
    if cred.status != "connected":
        return None
    try:
        access, refresh_tok = decrypt_tokens(cred)
    except Exception:
        cred.status = "needs-auth"
        return None
    if cred.expires_at and cred.expires_at <= utcnow() + timedelta(seconds=30):
        if not refresh_tok:
            cred.status = "needs-auth"
            return None
        oc = connector.oauth or {}
        try:
            meta = await oauth.discover(connector.url or "", oc)
            resp = await oauth.refresh(meta, refresh_token=refresh_tok, client_id=oc.get("client_id") or "",
                                       client_secret=oc.get("client_secret"), resource=oc.get("resource") or connector.url)
        except Exception:
            cred.status = "needs-auth"
            return None
        resp.setdefault("refresh_token", refresh_tok)
        await store_token(db, cred.user_id, cred.connector_id, resp)
        access, _ = decrypt_tokens(cred)
    return access


async def build_mcp_servers(db: AsyncSession, user: User, connector_ids: list[uuid.UUID] | None,
                            capabilities: dict[str, bool]) -> tuple[dict[str, dict[str, Any]], list[str], list[dict[str, Any]]]:
    """Returns (mcp_servers, allowed_tool_patterns, statuses). Connectors without a usable token are listed
    as needs-auth so the UI can prompt, but are not passed to the runtime (the run continues without them)."""
    if not capabilities.get("connectors", True):
        return {}, [], []
    q = select(Connector).where(Connector.approved.is_(True), Connector.enabled.is_(True))
    if connector_ids is not None:
        if not connector_ids:
            return {}, [], []
        q = q.where(Connector.id.in_(connector_ids))
    rows = (await db.execute(q)).scalars().all()
    servers: dict[str, dict[str, Any]] = {}
    patterns: list[str] = []
    statuses: list[dict[str, Any]] = []
    for c in rows:
        if not connector_visible_to(c, user):
            continue
        if c.transport == "stdio":
            if not capabilities.get("local_mcp", False):
                statuses.append({"connector_id": str(c.id), "name": c.name, "status": "disabled", "reason": "local stdio MCP disabled by org"})
                continue
            cmd = c.command or {}
            servers[c.name] = {"type": "stdio", "command": cmd.get("command", ""), "args": list(cmd.get("args", [])), "env": dict(cmd.get("env", {}))}
        elif c.transport in ("http", "sse"):
            headers: dict[str, str] = {}
            if c.auth_type == "oauth":
                cred = (await db.execute(select(ConnectorCredential).where(ConnectorCredential.user_id == user.id,
                                                                             ConnectorCredential.connector_id == c.id))).scalar_one_or_none()
                token = await access_token_for(db, cred, c) if cred else None
                if not token:
                    statuses.append({"connector_id": str(c.id), "name": c.name, "status": "needs-auth"})
                    continue
                headers["Authorization"] = f"{cred.token_type or 'Bearer'} {token}"
            elif c.auth_type == "static_header":
                headers.update((c.oauth or {}).get("headers", {}))
            servers[c.name] = {"type": c.transport, "url": c.url or "", "headers": headers}
            statuses.append({"connector_id": str(c.id), "name": c.name, "status": "connected"})
        elif c.transport == "sdk":
            servers[c.name] = {"type": "sdk_ref", "name": c.name}  # resolved by services.custom_tools
            statuses.append({"connector_id": str(c.id), "name": c.name, "status": "connected"})
        patterns.extend(c.allowed_tools or [f"mcp__{c.name}__*"])
        if c.denied_tools:
            patterns.extend(f"!{p}" for p in c.denied_tools)
    return servers, patterns, statuses
