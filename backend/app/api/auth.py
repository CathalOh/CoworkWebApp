from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import oidc
from app.auth.deps import client_ip, current_session, current_user, request_id, session_store
from app.auth.session import sign_cookie
from app.config import get_settings
from app.db import get_db
from app.models import Role, User
from app.schemas.common import UserOut
from app.security.audit import record_audit
from app.security.csrf import csrf_token_for

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _set_cookie(resp: Response, sid: str) -> None:
    s = get_settings()
    resp.set_cookie(s.session_cookie_name, sign_cookie(sid), max_age=s.session_ttl_seconds, httponly=True,
                    secure=s.cookie_secure, samesite="lax", path="/")


async def _upsert_user(db: AsyncSession, subject: str, email: str, name: str | None, roles: set[str]) -> User:
    user = (await db.execute(select(User).where(User.ping_subject == subject))).scalar_one_or_none()
    if user is None:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    role_rows = list((await db.execute(select(Role).where(Role.name.in_(list(roles))))).scalars().all())
    if user is None:
        user = User(ping_subject=subject, email=email, display_name=name, roles=role_rows, memberships=[])
        db.add(user)
        await db.flush()
    else:
        user.ping_subject, user.display_name = subject, name or user.display_name
        user.roles = role_rows
    await db.flush()
    return user


@router.get("/login")
async def login(request: Request):
    s = get_settings()
    if not s.oidc_issuer:
        if s.dev_login_enabled:
            return RedirectResponse(f"{s.frontend_origin}/login?dev=1")
        raise HTTPException(503, "OIDC not configured")
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    verifier, challenge = oidc.make_pkce()
    sid = await session_store(request).create({"pending": {"state": state, "nonce": nonce, "verifier": verifier}})
    resp = RedirectResponse(await oidc.authorize_url(state, nonce, challenge))
    _set_cookie(resp, sid)
    return resp


@router.get("/callback")
async def callback(request: Request, code: str, state: str, db: AsyncSession = Depends(get_db)):
    s = get_settings()
    sess = await current_session(request)
    if not sess or not sess[1].get("pending") or sess[1]["pending"].get("state") != state:
        raise HTTPException(400, "invalid state")
    sid, data = sess
    pending = data["pending"]
    tokens = await oidc.exchange_code(code, pending["verifier"])
    claims = await oidc.validate_id_token(tokens["id_token"], pending["nonce"])
    roles = oidc.roles_from_claims(claims)
    user = await _upsert_user(db, claims["sub"], claims.get("email") or f"{claims['sub']}@unknown", claims.get("name"), roles)
    await record_audit(db, action="session.start", actor_id=user.id, entity_type="user", entity_id=user.id, ip=client_ip(request),
                       request_id=request_id(request), after={"method": "oidc", "roles": sorted(roles)})
    await db.commit()
    await session_store(request).save(sid, {"user_id": str(user.id), "id_token": tokens.get("id_token"),
                                            "refresh_token": tokens.get("refresh_token")})
    resp = RedirectResponse(s.frontend_origin + "/")
    _set_cookie(resp, sid)
    return resp


class DevLogin(BaseModel):
    email: str
    display_name: str | None = None
    roles: list[str] = ["user"]


@router.post("/dev-login", response_model=UserOut)
async def dev_login(body: DevLogin, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Local development only: mints a session without PingID. Disabled when ENV=prod."""
    s = get_settings()
    if not s.dev_login_enabled:
        raise HTTPException(404, "not found")
    user = await _upsert_user(db, f"dev:{body.email}", body.email, body.display_name or body.email.split("@")[0], set(body.roles) | {"user"})
    await record_audit(db, action="session.start", actor_id=user.id, entity_type="user", entity_id=user.id, ip=client_ip(request),
                       request_id=request_id(request), after={"method": "dev"})
    await db.commit()
    sid = await session_store(request).create({"user_id": str(user.id)})
    _set_cookie(response, sid)
    return _user_out(user, sid)


@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    s = get_settings()
    sess = await current_session(request)
    url = None
    if sess:
        sid, data = sess
        await session_store(request).delete(sid)
        if data.get("user_id"):
            await record_audit(db, action="session.end", actor_id=uuid.UUID(data["user_id"]), entity_type="user",
                               entity_id=uuid.UUID(data["user_id"]), ip=client_ip(request), request_id=request_id(request))
            await db.commit()
        if s.oidc_issuer:
            url = await oidc.end_session_url(data.get("id_token"), s.frontend_origin + "/login")
    resp = Response(status_code=204) if not url else RedirectResponse(url, status_code=303)
    resp.delete_cookie(s.session_cookie_name, path="/")
    return resp


def _user_out(user: User, sid: str) -> UserOut:
    return UserOut(id=user.id, email=user.email, display_name=user.display_name, roles=sorted(user.role_names),
                   teams=sorted(user.team_ids, key=str), csrf_token=csrf_token_for(sid))


users_router = APIRouter(prefix="/v1/users", tags=["users"])


@users_router.get("/me", response_model=UserOut)
async def me(request: Request, user: User = Depends(current_user)):
    return _user_out(user, request.state.session_id)


@users_router.get("", response_model=list[UserOut])
async def list_users(q: str | None = None, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(User).order_by(User.email).limit(200)
    if q:
        stmt = stmt.where(User.email.ilike(f"%{q}%"))
    rows = (await db.execute(stmt)).scalars().all()
    return [UserOut(id=u.id, email=u.email, display_name=u.display_name, roles=sorted(u.role_names), teams=sorted(u.team_ids, key=str)) for u in rows]
