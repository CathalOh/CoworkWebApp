from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import client_ip, conversation_access, current_user, is_admin, request_id
from app.db import get_db
from app.models import Artifact, ArtifactVersion, Attachment, User
from app.schemas.extensions import ArtifactIn, ArtifactOut, ArtifactVersionOut
from app.security.audit import record_audit
from app.services import artifacts as svc
from app.services import objects

router = APIRouter(prefix="/v1", tags=["artifacts", "files"])


async def _artifact_for(db: AsyncSession, user: User, artifact_id: uuid.UUID, write: bool = False) -> Artifact:
    a = await db.get(Artifact, artifact_id)
    if not a:
        raise HTTPException(404, "artifact not found")
    if a.owner_id == user.id or is_admin(user):
        return a
    if a.conversation_id:
        await conversation_access(db, user, a.conversation_id, write=write)
        return a
    raise HTTPException(403, "no access")


@router.get("/artifacts", response_model=list[ArtifactOut])
async def list_artifacts(conversation_id: uuid.UUID | None = None, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    q = select(Artifact).where(Artifact.owner_id == user.id) if not conversation_id else select(Artifact).where(Artifact.conversation_id == conversation_id)
    if conversation_id:
        await conversation_access(db, user, conversation_id)
    return (await db.execute(q.order_by(Artifact.updated_at.desc()))).scalars().all()


@router.post("/artifacts", response_model=ArtifactOut, status_code=201)
async def create_artifact(body: ArtifactIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if body.conversation_id:
        await conversation_access(db, user, body.conversation_id, write=True)
    try:
        a = await svc.create_artifact(db, user.id, body.conversation_id, body.kind, body.title, body.content, body.live_source)
    except ValueError as exc:
        raise HTTPException(413 if "20 MB" in str(exc) else 400, str(exc)) from exc
    await db.commit()
    return a


@router.get("/artifacts/{artifact_id}", response_model=ArtifactOut)
async def get_artifact(artifact_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await _artifact_for(db, user, artifact_id)


@router.post("/artifacts/{artifact_id}/versions", response_model=ArtifactVersionOut, status_code=201)
async def new_version(artifact_id: uuid.UUID, body: dict, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    a = await _artifact_for(db, user, artifact_id, write=True)
    try:
        v = await svc.add_version(db, a, str(body.get("content", "")))
    except ValueError as exc:
        raise HTTPException(413, str(exc)) from exc
    await db.commit()
    return v


@router.get("/artifacts/{artifact_id}/versions", response_model=list[ArtifactVersionOut])
async def list_versions(artifact_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await _artifact_for(db, user, artifact_id)
    return (await db.execute(select(ArtifactVersion).where(ArtifactVersion.artifact_id == artifact_id).order_by(ArtifactVersion.version))).scalars().all()


@router.get("/artifacts/{artifact_id}/versions/{version}", response_model=ArtifactVersionOut)
async def get_version(artifact_id: uuid.UUID, version: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await _artifact_for(db, user, artifact_id)
    v = await svc.get_version(db, artifact_id, version)
    if not v:
        raise HTTPException(404, "version not found")
    return v


@router.get("/artifacts/{artifact_id}/render", response_class=HTMLResponse)
async def render(artifact_id: uuid.UUID, version: int | None = None, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Document for the sandboxed srcdoc iframe; served with the dedicated preview CSP (see security/headers.py)."""
    a = await _artifact_for(db, user, artifact_id)
    v = await svc.get_version(db, artifact_id, version)
    if not v:
        raise HTTPException(404, "version not found")
    return HTMLResponse(svc.render_document(a.kind, v.content))


@router.post("/artifacts/{artifact_id}/refresh", response_model=ArtifactVersionOut)
async def refresh_live(artifact_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Live Artifacts: re-run the artifact's data source (a backbone tool or connector query) and store a new version
    with the refreshed data embedded as window.__LIVE_DATA__."""
    import json

    from app.services.custom_tools import registry

    a = await _artifact_for(db, user, artifact_id, write=True)
    src = a.live_source or {}
    if not src.get("tool"):
        raise HTTPException(400, "artifact has no live source")
    server, _, tool = src["tool"].partition(".")
    spec = next((t for t in registry().get(server, []) if t.name == tool), None)
    if spec is None:
        raise HTTPException(400, "live source tool is not a registered backbone tool")
    data = await spec.fn(src.get("args") or {})
    cur = await svc.get_version(db, artifact_id, None)
    content = cur.content if cur else ""
    marker = "<!--LIVE_DATA-->"
    inject = f"{marker}<script>window.__LIVE_DATA__={json.dumps(data, default=str)}</script>"
    content = content.split(marker)[0] if marker in content else content
    v = await svc.add_version(db, a, content + inject)
    await record_audit(db, action="artifact.refreshed", actor_id=user.id, entity_type="artifact", entity_id=a.id,
                       request_id=request_id(request), ip=client_ip(request), after={"tool": src["tool"]})
    await db.commit()
    return v


@router.post("/files", status_code=201)
async def upload(request: Request, file: UploadFile = File(...), user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    data = await file.read()
    err = objects.validate_upload(file.filename or "upload", file.content_type, len(data))
    if err:
        raise HTTPException(415, err)
    key = await objects.put(data, file.filename or "")
    att = Attachment(owner_id=user.id, filename=file.filename or "upload", object_key=key, mime=file.content_type, bytes=len(data), scan_status="clean")
    db.add(att)
    await db.flush()
    await record_audit(db, action="file.uploaded", actor_id=user.id, entity_type="attachment", entity_id=att.id, request_id=request_id(request),
                       ip=client_ip(request), after={"filename": att.filename, "bytes": att.bytes, "mime": att.mime})
    await db.commit()
    return {"id": att.id, "filename": att.filename, "bytes": att.bytes, "mime": att.mime, "scan_status": att.scan_status}


@router.get("/files/{attachment_id}")
async def download(attachment_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    att = await db.get(Attachment, attachment_id)
    if not att or (att.owner_id != user.id and not is_admin(user)):
        raise HTTPException(404, "file not found")
    return FileResponse(objects.path_for(att.object_key), filename=att.filename, media_type=att.mime or "application/octet-stream")
