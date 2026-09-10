from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import client_ip, current_user, request_id
from app.config import get_settings
from app.db import get_db
from app.mcp_host import oauth
from app.mcp_host.registry import connector_visible_to, store_token
from app.models import Connector, ConnectorCredential, OAuthState, User
from app.models.base import utcnow
from app.schemas.extensions import ConnectorOut
from app.security.audit import record_audit

router = APIRouter(prefix="/v1/connectors", tags=["connectors"])


@router.get("", response_model=list[ConnectorOut])
async def catalog(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Connector).order_by(Connector.display_name))).scalars().all()
    creds = {c.connector_id: c for c in (await db.execute(select(ConnectorCredential).where(ConnectorCredential.user_id == user.id))).scalars().all()}
    out = []
    for c in rows:
        if not connector_visible_to(c, user):
            continue
        o = ConnectorOut.model_validate(c)
        if c.auth_type == "oauth":
            cred = creds.get(c.id)
            o.status = cred.status if cred else "needs-auth"
            if cred and cred.expires_at and cred.expires_at < utcnow() and not cred.enc_refresh_token:
                o.status = "needs-auth"
        else:
            o.status = "connected" if c.transport != "stdio" else "disabled"
        out.append(o)
    return out


@router.post("/{connector_id}/authorize")
async def authorize(connector_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Begin OAuth 2.1 + PKCE. Returns the authorization URL for the SPA to open."""
    s = get_settings()
    c = await db.get(Connector, connector_id)
    if not c or not connector_visible_to(c, user):
        raise HTTPException(404, "connector not found")
    if c.auth_type != "oauth":
        raise HTTPException(400, "connector does not use OAuth")
    oc = c.oauth or {}
    meta = await oauth.discover(c.url or "", oc)
    redirect_uri = f"{s.public_base_url}/v1/connectors/oauth/callback"
    client_id = oc.get("client_id")
    if not client_id:
        client_id = await oauth.register_client(meta, redirect_uri, f"{s.app_name} ({c.name})")
        c.oauth = {**oc, "client_id": client_id}
    verifier, challenge = oauth.make_pkce()
    state = secrets.token_urlsafe(32)
    resource = oc.get("resource") or c.url
    db.add(OAuthState(state=state, user_id=user.id, connector_id=c.id, code_verifier=verifier, redirect_uri=redirect_uri,
                      resource=resource, client_id=client_id, expires_at=utcnow() + timedelta(minutes=10)))
    await record_audit(db, action="connector.oauth.started", actor_id=user.id, entity_type="connector", entity_id=c.id,
                       request_id=request_id(request), ip=client_ip(request), after={"scopes": c.required_scopes})
    await db.commit()
    url = oauth.build_authorize_url(meta, client_id=client_id, redirect_uri=redirect_uri, scopes=list(c.required_scopes or []),
                                    state=state, code_challenge=challenge, resource=resource)
    return {"authorization_url": url, "state": state}


@router.get("/oauth/callback")
async def oauth_callback(request: Request, state: str, code: str | None = None, error: str | None = None,
                         error_description: str | None = None, db: AsyncSession = Depends(get_db)):
    s = get_settings()
    st = (await db.execute(select(OAuthState).where(OAuthState.state == state))).scalar_one_or_none()
    if not st or st.expires_at < utcnow():
        raise HTTPException(400, "invalid or expired state")
    c = await db.get(Connector, st.connector_id)
    await db.delete(st)
    if error or not code or not c:
        await record_audit(db, action="connector.oauth.failed", actor_id=st.user_id, entity_type="connector", entity_id=st.connector_id,
                           request_id=request_id(request), ip=client_ip(request), after={"error": error, "description": error_description})
        await db.commit()
        return RedirectResponse(f"{s.frontend_origin}/connectors?error={error or 'no_code'}")
    oc = c.oauth or {}
    meta = await oauth.discover(c.url or "", oc)
    tokens = await oauth.exchange_code(meta, code=code, client_id=st.client_id or oc.get("client_id") or "", client_secret=oc.get("client_secret"),
                                       redirect_uri=st.redirect_uri, code_verifier=st.code_verifier, resource=st.resource)
    await store_token(db, st.user_id, c.id, tokens)
    await record_audit(db, action="connector.oauth.completed", actor_id=st.user_id, entity_type="connector", entity_id=c.id,
                       request_id=request_id(request), ip=client_ip(request),
                       after={"scopes": (tokens.get("scope") or "").split(), "expires_in": tokens.get("expires_in")})
    await db.commit()
    return RedirectResponse(f"{s.frontend_origin}/connectors?connected={c.name}")


@router.delete("/{connector_id}/credentials", status_code=204)
async def revoke(connector_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    cred = (await db.execute(select(ConnectorCredential).where(ConnectorCredential.user_id == user.id,
                                                                 ConnectorCredential.connector_id == connector_id))).scalar_one_or_none()
    if cred:
        await db.delete(cred)
        await record_audit(db, action="connector.credentials_revoked", actor_id=user.id, entity_type="connector", entity_id=connector_id,
                           request_id=request_id(request), ip=client_ip(request))
    await db.commit()
