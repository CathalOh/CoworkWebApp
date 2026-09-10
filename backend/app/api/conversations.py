from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.auth.deps import client_ip, conversation_access, current_user, is_admin, request_id
from app.auth.session import unsign_cookie
from app.config import get_settings
from app.db import db_session, get_db
from app.models import Approval, ContentBlock, Conversation, Message, Run, RunEvent, User
from app.orchestration.events import TERMINAL_TYPES, get_event_bus
from app.schemas.chat import (
    ApprovalIn,
    ApprovalOut,
    ConversationIn,
    ConversationOut,
    ConversationPatch,
    ElicitationIn,
    MessageIn,
    MessageOut,
    RunOut,
)
from app.security.audit import record_audit
from app.services.runs import RunRejected, start_run
from app.tasks.queue import enqueue

router = APIRouter(prefix="/v1", tags=["conversations"])
ACTIVE = ("queued", "running", "waiting_approval", "waiting_elicitation")


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(project_id: uuid.UUID | None = None, archived: bool = False, user: User = Depends(current_user),
                             db: AsyncSession = Depends(get_db)):
    teams = list(user.team_ids) or [uuid.uuid4()]
    q = select(Conversation).where(or_(Conversation.user_id == user.id, Conversation.shared_with_team.in_(teams)),
                                   Conversation.archived.is_(archived))
    if project_id:
        q = q.where(Conversation.project_id == project_id)
    return (await db.execute(q.order_by(Conversation.updated_at.desc()).limit(200))).scalars().all()


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(body: ConversationIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    from app.auth.deps import project_access, workspace_access

    if body.project_id:
        await project_access(db, user, body.project_id)
    if body.workspace_id:
        await workspace_access(db, user, body.workspace_id)
    c = Conversation(user_id=user.id, title=body.title, project_id=body.project_id, workspace_id=body.workspace_id,
                     permission_mode=body.permission_mode, connector_ids=[str(x) for x in body.connector_ids] if body.connector_ids is not None else None,
                     skill_names=body.skill_names)
    db.add(c)
    await db.commit()
    return c


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(conversation_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await conversation_access(db, user, conversation_id)


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def patch_conversation(conversation_id: uuid.UUID, body: ConversationPatch, request: Request, user: User = Depends(current_user),
                             db: AsyncSession = Depends(get_db)):
    c = await conversation_access(db, user, conversation_id, write=True)
    data = body.model_dump(exclude_unset=True)
    if "shared_with_team" in data and data["shared_with_team"] and data["shared_with_team"] not in user.team_ids and not is_admin(user):
        raise HTTPException(403, "you can only share with your own teams")
    if "connector_ids" in data and data["connector_ids"] is not None:
        data["connector_ids"] = [str(x) for x in data["connector_ids"]]
    for k, v in data.items():
        setattr(c, k, v)
    if "shared_with_team" in data:
        await record_audit(db, action="conversation.shared", actor_id=user.id, entity_type="conversation", entity_id=c.id,
                           request_id=request_id(request), ip=client_ip(request), after={"team_id": str(data["shared_with_team"])})
    await db.commit()
    return c


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    c = await conversation_access(db, user, conversation_id, write=True)
    await record_audit(db, action="conversation.deleted", actor_id=user.id, entity_type="conversation", entity_id=c.id,
                       request_id=request_id(request), ip=client_ip(request), before={"title": c.title})
    await db.delete(c)
    await db.commit()


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(conversation_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await conversation_access(db, user, conversation_id)
    msgs = (await db.execute(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.seq))).scalars().all()
    ids = [m.id for m in msgs]
    blocks = (await db.execute(select(ContentBlock).where(ContentBlock.message_id.in_(ids or [uuid.uuid4()])).order_by(ContentBlock.ord))).scalars().all()
    by_msg: dict[uuid.UUID, list] = {}
    for b in blocks:
        by_msg.setdefault(b.message_id, []).append(b)
    return [MessageOut(id=m.id, role=m.role, seq=m.seq, run_id=m.run_id, created_at=m.created_at, blocks=by_msg.get(m.id, [])) for m in msgs]


@router.post("/conversations/{conversation_id}/messages", response_model=RunOut, status_code=202)
async def post_message(conversation_id: uuid.UUID, body: MessageIn, request: Request, user: User = Depends(current_user),
                       db: AsyncSession = Depends(get_db)):
    c = await conversation_access(db, user, conversation_id, write=True)
    active = (await db.execute(select(Run).where(Run.conversation_id == conversation_id, Run.status.in_(ACTIVE)))).scalars().first()
    if active:
        raise HTTPException(409, f"a run is already {active.status} for this conversation")
    cfg = {k: v for k, v in {"max_budget_usd": body.max_budget_usd, "model": body.model, "effort": body.effort,
                             "attachment_ids": [str(a) for a in body.attachment_ids] if body.attachment_ids else None}.items() if v is not None}
    try:
        run = await start_run(db, conversation=c, user=user, prompt=body.content, permission_mode=body.permission_mode, config=cfg,
                              request_id=request_id(request), ip=client_ip(request))
    except RunRejected as exc:
        raise HTTPException(exc.status, exc.reason) from exc
    await db.commit()
    await enqueue("execute_run", str(run.id))
    return run


@router.get("/conversations/{conversation_id}/runs", response_model=list[RunOut])
async def list_runs(conversation_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await conversation_access(db, user, conversation_id)
    return (await db.execute(select(Run).where(Run.conversation_id == conversation_id).order_by(Run.created_at.desc()))).scalars().all()


async def _run_for(db: AsyncSession, user: User, run_id: uuid.UUID, write: bool = False) -> Run:
    run = await db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    await conversation_access(db, user, run.conversation_id, write=write)
    return run


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await _run_for(db, user, run_id)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """SSE stream, resumable: send Last-Event-ID (or ?after=) to resume from that seq with no duplicates."""
    run = await _run_for(db, user, run_id)
    try:
        after = int(request.headers.get("last-event-id") or request.query_params.get("after") or 0)
    except ValueError:
        after = 0
    conversation_id = run.conversation_id

    async def gen():
        last = after
        # 1. replay durable history from the DB (covers events older than the Redis retention window)
        async with db_session() as s:
            rows = (await s.execute(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.seq > last).order_by(RunEvent.seq))).scalars().all()
            for r in rows:
                last = r.seq
                yield {"id": str(r.seq), "event": "message", "data": json.dumps({"run_id": str(run_id), "seq": r.seq, "type": r.type,
                                                                                  "data": r.data, "ts": r.ts.isoformat()})}
                if r.type in TERMINAL_TYPES:
                    return
            fresh = await s.get(Run, run_id)
            if fresh and fresh.status not in ACTIVE and fresh.last_seq <= last:
                yield {"id": str(last), "event": "message", "data": json.dumps({"run_id": str(run_id), "seq": last, "type": "status",
                                                                                "data": {"kind": "closed", "status": fresh.status}})}
                return
        # 2. follow the live stream
        bus = await get_event_bus()
        async for ev in bus.read(str(run_id), after_seq=last, timeout=None):
            if await request.is_disconnected():
                return
            if ev.seq <= last:
                continue
            last = ev.seq
            yield {"id": str(ev.seq), "event": "message", "data": json.dumps(ev.to_dict(), default=str)}

    return EventSourceResponse(gen(), ping=15, headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                                        "X-Conversation-Id": str(conversation_id)})


@router.post("/runs/{run_id}/interrupt", status_code=202)
async def interrupt_run(run_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    run = await _run_for(db, user, run_id, write=True)
    if run.status not in ACTIVE:
        raise HTTPException(409, "run is not active")
    bus = await get_event_bus()
    await bus.send_control(str(run_id), {"type": "interrupt", "user_id": str(user.id)})
    await record_audit(db, action="run.interrupt_requested", actor_id=user.id, entity_type="run", entity_id=run_id,
                       request_id=request_id(request), ip=client_ip(request))
    await db.commit()
    return {"ok": True}


@router.get("/runs/{run_id}/approvals", response_model=list[ApprovalOut])
async def list_approvals(run_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await _run_for(db, user, run_id)
    return (await db.execute(select(Approval).where(Approval.run_id == run_id).order_by(Approval.created_at))).scalars().all()


@router.post("/runs/{run_id}/approvals", status_code=202)
async def submit_approval(run_id: uuid.UUID, body: ApprovalIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await _run_for(db, user, run_id, write=True)
    bus = await get_event_bus()
    await bus.send_control(str(run_id), {"type": "approval", "tool_use_id": body.tool_use_id, "decision": body.decision,
                                         "rewrite": body.rewrite, "user_id": str(user.id)})
    return {"ok": True}


@router.post("/runs/{run_id}/elicitations", status_code=202)
async def submit_elicitation(run_id: uuid.UUID, body: ElicitationIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await _run_for(db, user, run_id, write=True)
    bus = await get_event_bus()
    await bus.send_control(str(run_id), {"type": "elicitation", "elicitation_id": body.elicitation_id,
                                         "response": {"action": body.action, "content": body.content}, "user_id": str(user.id)})
    return {"ok": True}


@router.websocket("/runs/{run_id}/ws")
async def run_ws(websocket: WebSocket, run_id: uuid.UUID):
    """Bidirectional channel for approvals/steering. Auth = the same session cookie; origin must match the SPA."""
    s = get_settings()
    origin = websocket.headers.get("origin")
    if origin and origin not in (s.frontend_origin, s.public_base_url):
        await websocket.close(code=4403)
        return
    sid = unsign_cookie(websocket.cookies.get(s.session_cookie_name))
    data = await websocket.app.state.sessions.load(sid) if sid else None
    if not data:
        await websocket.close(code=4401)
        return
    async with db_session() as db:
        user = await db.get(User, uuid.UUID(data["user_id"]))
        try:
            run = await _run_for(db, user, run_id, write=True)
        except HTTPException:
            await websocket.close(code=4403)
            return
        after = run.last_seq if run.status not in ACTIVE else 0
    await websocket.accept()
    bus = await get_event_bus()

    async def pump():
        async for ev in bus.read(str(run_id), after_seq=after, timeout=None):
            await websocket.send_text(json.dumps(ev.to_dict(), default=str))

    task = asyncio.create_task(pump())
    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            kind = msg.get("type")
            if kind in ("approval", "elicitation", "interrupt"):
                msg["user_id"] = str(user.id)
                await bus.send_control(str(run_id), msg)
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
