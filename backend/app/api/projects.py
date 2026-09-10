from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import client_ip, current_user, is_admin, project_access, request_id
from app.db import get_db
from app.models import Project, ProjectFile, ProjectShare, User
from app.schemas.common import ProjectFileOut, ProjectIn, ProjectOut, ProjectPatch, ShareIn
from app.security.audit import record_audit
from app.services import objects

router = APIRouter(prefix="/v1/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
async def list_projects(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    teams = list(user.team_ids) or [uuid.uuid4()]
    shared = select(ProjectShare.project_id).where(ProjectShare.team_id.in_(teams))
    q = select(Project).where(or_(Project.owner_id == user.id, Project.team_id.in_(teams), Project.id.in_(shared)))
    if is_admin(user):
        q = select(Project)
    return (await db.execute(q.order_by(Project.updated_at.desc()))).scalars().all()


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectIn, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if body.team_id and body.team_id not in user.team_ids and not is_admin(user):
        raise HTTPException(403, "not a member of that team")
    p = Project(owner_id=user.id, **body.model_dump())
    db.add(p)
    await db.flush()
    await record_audit(db, action="project.created", actor_id=user.id, entity_type="project", entity_id=p.id, request_id=request_id(request),
                       ip=client_ip(request), after={"name": p.name})
    await db.commit()
    return p


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await project_access(db, user, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
async def patch_project(project_id: uuid.UUID, body: ProjectPatch, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    p = await project_access(db, user, project_id, write=True)
    before = {"name": p.name, "memory_enabled": p.memory_enabled}
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    await record_audit(db, action="project.updated", actor_id=user.id, entity_type="project", entity_id=p.id, request_id=request_id(request),
                       ip=client_ip(request), before=before, after=body.model_dump(exclude_unset=True, mode="json"))
    await db.commit()
    return p


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    p = await project_access(db, user, project_id, write=True)
    if p.owner_id != user.id and not is_admin(user):
        raise HTTPException(403, "owner or admin required")
    await record_audit(db, action="project.deleted", actor_id=user.id, entity_type="project", entity_id=p.id, request_id=request_id(request),
                       ip=client_ip(request), before={"name": p.name})
    await db.delete(p)
    await db.commit()


@router.get("/{project_id}/files", response_model=list[ProjectFileOut])
async def list_files(project_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await project_access(db, user, project_id)
    return (await db.execute(select(ProjectFile).where(ProjectFile.project_id == project_id).order_by(ProjectFile.path))).scalars().all()


@router.post("/{project_id}/files", response_model=ProjectFileOut, status_code=201)
async def upload_file(project_id: uuid.UUID, request: Request, file: UploadFile = File(...), user: User = Depends(current_user),
                      db: AsyncSession = Depends(get_db)):
    await project_access(db, user, project_id, write=True)
    data = await file.read()
    err = objects.validate_upload(file.filename or "upload", file.content_type, len(data))
    if err:
        raise HTTPException(415, err)
    key = await objects.put(data, file.filename or "")
    pf = ProjectFile(project_id=project_id, path=file.filename or "upload", object_key=key, bytes=len(data), mime=file.content_type)
    db.add(pf)
    await db.flush()
    await record_audit(db, action="project.file_uploaded", actor_id=user.id, entity_type="project", entity_id=project_id,
                       request_id=request_id(request), ip=client_ip(request), after={"path": pf.path, "bytes": pf.bytes})
    await db.commit()
    return pf


@router.get("/{project_id}/files/{file_id}")
async def download_file(project_id: uuid.UUID, file_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await project_access(db, user, project_id)
    pf = await db.get(ProjectFile, file_id)
    if not pf or pf.project_id != project_id:
        raise HTTPException(404, "file not found")
    return FileResponse(objects.path_for(pf.object_key), filename=pf.path, media_type=pf.mime or "application/octet-stream")


@router.delete("/{project_id}/files/{file_id}", status_code=204)
async def delete_file(project_id: uuid.UUID, file_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await project_access(db, user, project_id, write=True)
    pf = await db.get(ProjectFile, file_id)
    if not pf or pf.project_id != project_id:
        raise HTTPException(404, "file not found")
    await record_audit(db, action="project.file_deleted", actor_id=user.id, entity_type="project", entity_id=project_id,
                       request_id=request_id(request), ip=client_ip(request), before={"path": pf.path})
    await db.delete(pf)
    await db.commit()


@router.get("/{project_id}/shares")
async def list_shares(project_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await project_access(db, user, project_id)
    rows = (await db.execute(select(ProjectShare).where(ProjectShare.project_id == project_id))).scalars().all()
    return [{"team_id": r.team_id, "access": r.access, "share_memory": r.share_memory} for r in rows]


@router.post("/{project_id}/shares", status_code=204)
async def share_project(project_id: uuid.UUID, body: ShareIn, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    p = await project_access(db, user, project_id, write=True)
    if not (p.owner_id == user.id or is_admin(user) or "team_lead" in user.role_names):
        raise HTTPException(403, "owner, team lead or admin required")
    if body.team_id not in user.team_ids and not is_admin(user):
        raise HTTPException(403, "you can only share with your own teams")
    existing = (await db.execute(select(ProjectShare).where(ProjectShare.project_id == project_id, ProjectShare.team_id == body.team_id))).scalar_one_or_none()
    if existing:
        existing.access, existing.share_memory = body.access, body.share_memory
    else:
        db.add(ProjectShare(project_id=project_id, team_id=body.team_id, access=body.access, share_memory=body.share_memory))
    await record_audit(db, action="project.shared", actor_id=user.id, entity_type="project", entity_id=project_id, request_id=request_id(request),
                       ip=client_ip(request), after=body.model_dump(mode="json"))
    await db.commit()


@router.delete("/{project_id}/shares/{team_id}", status_code=204)
async def unshare_project(project_id: uuid.UUID, team_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await project_access(db, user, project_id, write=True)
    existing = (await db.execute(select(ProjectShare).where(ProjectShare.project_id == project_id, ProjectShare.team_id == team_id))).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await record_audit(db, action="project.unshared", actor_id=user.id, entity_type="project", entity_id=project_id,
                           request_id=request_id(request), ip=client_ip(request), before={"team_id": str(team_id)})
    await db.commit()
