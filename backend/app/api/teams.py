from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import client_ip, current_user, is_admin, request_id, require_roles, workspace_access
from app.db import get_db
from app.models import Membership, Team, User, Workspace
from app.sandbox.workspaces import dir_size, workspace_dir
from app.schemas.common import MembershipIn, TeamIn, TeamOut, UserOut, WorkspaceIn, WorkspaceOut
from app.security.audit import record_audit

router = APIRouter(prefix="/v1/teams", tags=["teams"])


@router.get("", response_model=list[TeamOut])
async def list_teams(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if is_admin(user):
        return (await db.execute(select(Team).order_by(Team.name))).scalars().all()
    return (await db.execute(select(Team).where(Team.id.in_(list(user.team_ids) or [uuid.uuid4()])))).scalars().all()


@router.post("", response_model=TeamOut, status_code=201)
async def create_team(body: TeamIn, request: Request, user: User = Depends(require_roles("org_admin", "team_lead", "workspace_admin")),
                      db: AsyncSession = Depends(get_db)):
    t = Team(name=body.name)
    db.add(t)
    await db.flush()
    db.add(Membership(team_id=t.id, user_id=user.id, team_role="lead"))
    await record_audit(db, action="team.created", actor_id=user.id, entity_type="team", entity_id=t.id, request_id=request_id(request),
                       ip=client_ip(request), after={"name": t.name})
    await db.commit()
    return t


@router.get("/{team_id}/members", response_model=list[UserOut])
async def members(team_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if team_id not in user.team_ids and not is_admin(user):
        raise HTTPException(403, "not a member")
    rows = (await db.execute(select(User).join(Membership, Membership.user_id == User.id).where(Membership.team_id == team_id))).scalars().all()
    return [UserOut(id=u.id, email=u.email, display_name=u.display_name, roles=sorted(u.role_names), teams=sorted(u.team_ids, key=str)) for u in rows]


@router.post("/{team_id}/members", status_code=204)
async def add_member(team_id: uuid.UUID, body: MembershipIn, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    lead = any(m.team_id == team_id and m.team_role == "lead" for m in user.memberships)
    if not (lead or is_admin(user) or "team_lead" in user.role_names and team_id in user.team_ids):
        raise HTTPException(403, "team lead required")
    if not await db.get(Team, team_id) or not await db.get(User, body.user_id):
        raise HTTPException(404, "team or user not found")
    existing = await db.get(Membership, {"team_id": team_id, "user_id": body.user_id})
    if existing:
        existing.team_role = body.team_role
    else:
        db.add(Membership(team_id=team_id, user_id=body.user_id, team_role=body.team_role))
    await record_audit(db, action="team.member_added", actor_id=user.id, entity_type="team", entity_id=team_id, request_id=request_id(request),
                       ip=client_ip(request), after={"user_id": str(body.user_id), "team_role": body.team_role})
    await db.commit()


@router.delete("/{team_id}/members/{user_id}", status_code=204)
async def remove_member(team_id: uuid.UUID, user_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    lead = any(m.team_id == team_id and m.team_role == "lead" for m in user.memberships)
    if not (lead or is_admin(user)):
        raise HTTPException(403, "team lead required")
    m = await db.get(Membership, {"team_id": team_id, "user_id": user_id})
    if m:
        await db.delete(m)
        await record_audit(db, action="team.member_removed", actor_id=user.id, entity_type="team", entity_id=team_id,
                           request_id=request_id(request), ip=client_ip(request), after={"user_id": str(user_id)})
    await db.commit()


ws_router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])


@ws_router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if is_admin(user) or "workspace_admin" in user.role_names:
        return (await db.execute(select(Workspace).order_by(Workspace.created_at.desc()))).scalars().all()
    q = select(Workspace).where((Workspace.owner_id == user.id) | (Workspace.team_id.in_(list(user.team_ids) or [uuid.uuid4()])))
    return (await db.execute(q.order_by(Workspace.created_at.desc()))).scalars().all()


@ws_router.post("", response_model=WorkspaceOut, status_code=201)
async def create_workspace(body: WorkspaceIn, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if body.team_id and body.team_id not in user.team_ids and not is_admin(user) and "workspace_admin" not in user.role_names:
        raise HTTPException(403, "not a member of that team")
    w = Workspace(name=body.name, owner_id=user.id, team_id=body.team_id, host_path="", quota_bytes=body.quota_bytes,
                  network_policy=body.network_policy)
    db.add(w)
    await db.flush()
    w.host_path = str(workspace_dir(w.id))
    await record_audit(db, action="workspace.created", actor_id=user.id, entity_type="workspace", entity_id=w.id,
                       request_id=request_id(request), ip=client_ip(request), after={"name": w.name, "team_id": str(body.team_id) if body.team_id else None})
    await db.commit()
    return w


@ws_router.get("/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(workspace_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await workspace_access(db, user, workspace_id)


@ws_router.get("/{workspace_id}/files")
async def list_workspace_files(workspace_id: uuid.UUID, path: str = "", user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    from app.sandbox.workspaces import safe_join

    w = await workspace_access(db, user, workspace_id)
    root = workspace_dir(w.id)
    target = safe_join(root, path)
    if not target.exists():
        return {"path": path, "entries": [], "bytes_used": dir_size(root)}
    entries = []
    for p in sorted(target.iterdir()):
        if p.name.startswith(".claude") or p.name == ".plugins":
            continue
        st = p.stat()
        entries.append({"name": p.name, "is_dir": p.is_dir(), "bytes": st.st_size if p.is_file() else None, "mtime": st.st_mtime})
    return {"path": path, "entries": entries, "bytes_used": dir_size(root), "quota_bytes": w.quota_bytes}


@ws_router.get("/{workspace_id}/files/content")
async def read_workspace_file(workspace_id: uuid.UUID, path: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    from fastapi.responses import FileResponse

    from app.sandbox.workspaces import safe_join

    w = await workspace_access(db, user, workspace_id)
    target = safe_join(workspace_dir(w.id), path)
    if not target.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(target, filename=target.name)


@ws_router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(workspace_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    w = await workspace_access(db, user, workspace_id, write=True)
    if w.owner_id != user.id and not is_admin(user):
        raise HTTPException(403, "owner or admin required")
    await record_audit(db, action="workspace.deleted", actor_id=user.id, entity_type="workspace", entity_id=w.id,
                       request_id=request_id(request), ip=client_ip(request), before={"name": w.name, "host_path": w.host_path})
    await db.delete(w)  # files are retained on disk for the retention runbook; metadata row removed
    await db.commit()
