"""FastAPI dependencies: current user, RBAC guards, CSRF for mutating requests, resource access helpers."""
from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session import SessionStore, unsign_cookie
from app.config import get_settings
from app.db import get_db
from app.models import Conversation, Project, ProjectShare, User, Workspace
from app.security.csrf import csrf_valid

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def session_store(request: Request) -> SessionStore:
    return request.app.state.sessions


async def current_session(request: Request) -> tuple[str, dict] | None:
    sid = unsign_cookie(request.cookies.get(get_settings().session_cookie_name))
    if not sid:
        return None
    data = await session_store(request).load(sid)
    return (sid, data) if data else None


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    sess = await current_session(request)
    if not sess:
        raise HTTPException(401, "not authenticated")
    sid, data = sess
    if request.method in MUTATING and not request.url.path.startswith("/v1/auth/"):
        if not csrf_valid(sid, request.headers.get(get_settings().csrf_header_name)):
            raise HTTPException(403, "invalid CSRF token")
    user = await db.get(User, uuid.UUID(data["user_id"]))
    if not user or user.status != "active":
        raise HTTPException(401, "user inactive")
    request.state.user = user
    request.state.session_id = sid
    request.state.session = data
    return user


def require_roles(*roles: str) -> Callable:
    async def dep(user: User = Depends(current_user)) -> User:
        if not (user.role_names & set(roles)):
            raise HTTPException(403, f"requires one of roles: {', '.join(roles)}")
        return user
    return dep


def is_admin(user: User) -> bool:
    return "org_admin" in user.role_names


async def project_access(db: AsyncSession, user: User, project_id: uuid.UUID, write: bool = False) -> Project:
    p = await db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "project not found")
    if p.owner_id == user.id or is_admin(user):
        return p
    if p.team_id and p.team_id in user.team_ids and (not write or _is_lead(user, p.team_id)):
        return p
    shares = (await db.execute(select(ProjectShare).where(ProjectShare.project_id == project_id,
                                                          ProjectShare.team_id.in_(list(user.team_ids) or [uuid.uuid4()])))).scalars().all()
    if any((not write) or s.access == "write" for s in shares):
        return p
    raise HTTPException(403, "no access to project")


def _is_lead(user: User, team_id: uuid.UUID) -> bool:
    return any(m.team_id == team_id and m.team_role == "lead" for m in user.memberships) or "team_lead" in user.role_names


async def conversation_access(db: AsyncSession, user: User, conversation_id: uuid.UUID, write: bool = False) -> Conversation:
    c = await db.get(Conversation, conversation_id)
    if not c:
        raise HTTPException(404, "conversation not found")
    if c.user_id == user.id or is_admin(user):
        return c
    if not write and c.shared_with_team and c.shared_with_team in user.team_ids:
        return c
    raise HTTPException(403, "no access to conversation")


async def workspace_access(db: AsyncSession, user: User, workspace_id: uuid.UUID, write: bool = False) -> Workspace:
    w = await db.get(Workspace, workspace_id)
    if not w:
        raise HTTPException(404, "workspace not found")
    if w.owner_id == user.id or is_admin(user) or "workspace_admin" in user.role_names:
        return w
    if w.team_id and w.team_id in user.team_ids:
        return w
    raise HTTPException(403, "no access to workspace")


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None))


def request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)
