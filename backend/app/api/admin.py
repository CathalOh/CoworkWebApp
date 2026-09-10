from __future__ import annotations

import base64
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import client_ip, request_id, require_roles
from app.db import get_db
from app.models import AppLog, AuditEvent, Connector, LlmRequestLog, Role, Run, User
from app.schemas.extensions import CapabilityIn, ConnectorIn, ConnectorOut
from app.security.audit import record_audit, verify_chain
from app.services.capabilities import DEFAULTS, get_capabilities, set_capability
from app.services.usage import usage_summary

router = APIRouter(prefix="/v1/admin", tags=["admin"])
AUDIT_ROLES = ("org_admin", "auditor")


def _cursor(v: int | None) -> str | None:
    return base64.urlsafe_b64encode(str(v).encode()).decode() if v else None


def _decode(c: str | None) -> int | None:
    return int(base64.urlsafe_b64decode(c.encode())) if c else None


@router.get("/audit")
async def audit(actor_id: uuid.UUID | None = None, action: str | None = None, entity_type: str | None = None, entity_id: uuid.UUID | None = None,
                since: datetime | None = None, until: datetime | None = None, cursor: str | None = None, limit: int = 100,
                user: User = Depends(require_roles(*AUDIT_ROLES)), db: AsyncSession = Depends(get_db)):
    limit = max(1, min(limit, 500))
    q = select(AuditEvent).order_by(AuditEvent.id.desc())
    if actor_id:
        q = q.where(AuditEvent.actor_id == actor_id)
    if action:
        q = q.where(AuditEvent.action.like(f"{action}%"))
    if entity_type:
        q = q.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditEvent.entity_id == entity_id)
    if since:
        q = q.where(AuditEvent.ts >= since)
    if until:
        q = q.where(AuditEvent.ts <= until)
    c = _decode(cursor)
    if c:
        q = q.where(AuditEvent.id < c)
    rows = (await db.execute(q.limit(limit + 1))).scalars().all()
    nxt = _cursor(rows[limit - 1].id) if len(rows) > limit else None
    items = [{"id": r.id, "ts": r.ts, "actor_id": r.actor_id, "actor_type": r.actor_type, "action": r.action, "entity_type": r.entity_type,
              "entity_id": r.entity_id, "request_id": r.request_id, "ip": r.ip, "before": r.before, "after": r.after,
              "stream_key": r.stream_key, "row_hash": r.row_hash.hex() if r.row_hash else None} for r in rows[:limit]]
    return {"items": items, "next_cursor": nxt}


@router.get("/audit/verify")
async def audit_verify(stream_key: str | None = None, user: User = Depends(require_roles(*AUDIT_ROLES)), db: AsyncSession = Depends(get_db)):
    return await verify_chain(db, stream_key)


@router.get("/audit/export")
async def audit_export(since: datetime | None = None, user: User = Depends(require_roles(*AUDIT_ROLES)), db: AsyncSession = Depends(get_db)):
    """JSON-lines export for compliance tooling (the thing hosted Cowork does not offer)."""
    import json

    from fastapi.responses import StreamingResponse

    q = select(AuditEvent).order_by(AuditEvent.id)
    if since:
        q = q.where(AuditEvent.ts >= since)

    async def gen():
        result = await db.stream(q)
        async for (r,) in result:
            yield json.dumps({"id": r.id, "ts": r.ts.isoformat(), "actor_id": str(r.actor_id) if r.actor_id else None, "actor_type": r.actor_type,
                              "action": r.action, "entity_type": r.entity_type, "entity_id": str(r.entity_id) if r.entity_id else None,
                              "request_id": r.request_id, "ip": r.ip, "before": r.before, "after": r.after,
                              "prev_hash": r.prev_hash.hex() if r.prev_hash else None, "row_hash": r.row_hash.hex()}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.get("/llm-logs")
async def llm_logs(user_id: uuid.UUID | None = None, run_id: uuid.UUID | None = None, cursor: str | None = None, limit: int = 100,
                   user: User = Depends(require_roles(*AUDIT_ROLES)), db: AsyncSession = Depends(get_db)):
    limit = max(1, min(limit, 500))
    q = select(LlmRequestLog).order_by(LlmRequestLog.id.desc())
    if user_id:
        q = q.where(LlmRequestLog.user_id == user_id)
    if run_id:
        q = q.where(LlmRequestLog.run_id == run_id)
    c = _decode(cursor)
    if c:
        q = q.where(LlmRequestLog.id < c)
    rows = (await db.execute(q.limit(limit + 1))).scalars().all()
    return {"items": [{"id": r.id, "ts": r.ts, "run_id": r.run_id, "user_id": r.user_id, "model_id": r.model_id, "request": r.request,
                       "response": r.response, "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
                       "cache_read_tokens": r.cache_read_tokens, "cost_usd": float(r.cost_usd) if r.cost_usd is not None else None,
                       "latency_ms": r.latency_ms} for r in rows[:limit]],
            "next_cursor": _cursor(rows[limit - 1].id) if len(rows) > limit else None}


@router.get("/app-logs")
async def app_logs(level: str | None = None, request_id_filter: str | None = None, cursor: str | None = None, limit: int = 200,
                   user: User = Depends(require_roles(*AUDIT_ROLES)), db: AsyncSession = Depends(get_db)):
    limit = max(1, min(limit, 1000))
    q = select(AppLog).order_by(AppLog.id.desc())
    if level:
        q = q.where(AppLog.level == level)
    if request_id_filter:
        q = q.where(AppLog.request_id == request_id_filter)
    c = _decode(cursor)
    if c:
        q = q.where(AppLog.id < c)
    rows = (await db.execute(q.limit(limit + 1))).scalars().all()
    return {"items": [{"id": r.id, "ts": r.ts, "level": r.level, "logger": r.logger, "message": r.message, "context": r.context,
                       "request_id": r.request_id} for r in rows[:limit]],
            "next_cursor": _cursor(rows[limit - 1].id) if len(rows) > limit else None}


@router.get("/usage")
async def usage(group_by: str = "user", days: int = 30, user: User = Depends(require_roles("org_admin", "auditor", "workspace_admin", "team_lead")),
                db: AsyncSession = Depends(get_db)):
    if group_by not in ("user", "team", "project", "model"):
        raise HTTPException(400, "group_by must be user|team|project|model")
    return {"group_by": group_by, "days": days, "items": await usage_summary(db, group_by, days)}


@router.get("/runs")
async def active_runs(status: str | None = None, limit: int = 100, user: User = Depends(require_roles("org_admin")), db: AsyncSession = Depends(get_db)):
    q = select(Run).order_by(Run.created_at.desc()).limit(min(limit, 500))
    if status:
        q = q.where(Run.status == status)
    rows = (await db.execute(q)).scalars().all()
    return [{"id": r.id, "user_id": r.user_id, "conversation_id": r.conversation_id, "status": r.status, "permission_mode": r.permission_mode,
             "started_at": r.started_at, "ended_at": r.ended_at, "total_cost_usd": float(r.total_cost_usd) if r.total_cost_usd is not None else None,
             "error": r.error} for r in rows]


@router.get("/capabilities")
async def capabilities(user: User = Depends(require_roles("org_admin", "workspace_admin", "auditor")), db: AsyncSession = Depends(get_db)):
    return {"capabilities": await get_capabilities(db), "known": sorted(DEFAULTS)}


@router.post("/capabilities")
async def set_capabilities(body: CapabilityIn, request: Request, user: User = Depends(require_roles("org_admin")), db: AsyncSession = Depends(get_db)):
    try:
        row = await set_capability(db, body.key, body.enabled, body.reason, user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await record_audit(db, action="capability.changed", actor_id=user.id, entity_type="capability", request_id=request_id(request), ip=client_ip(request),
                       after={"key": row.key, "enabled": row.enabled, "reason": row.reason})
    await db.commit()
    return {"key": row.key, "enabled": row.enabled, "reason": row.reason}


@router.get("/connectors", response_model=list[ConnectorOut])
async def admin_connectors(user: User = Depends(require_roles("org_admin", "workspace_admin")), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Connector).order_by(Connector.display_name))).scalars().all()


@router.post("/connectors", response_model=ConnectorOut, status_code=201)
async def create_connector(body: ConnectorIn, request: Request, user: User = Depends(require_roles("org_admin")), db: AsyncSession = Depends(get_db)):
    data = body.model_dump(mode="json")
    c = Connector(**data)
    db.add(c)
    await db.flush()
    await record_audit(db, action="connector.created", actor_id=user.id, entity_type="connector", entity_id=c.id, request_id=request_id(request),
                       ip=client_ip(request), after={k: v for k, v in data.items() if k != "oauth"})
    await db.commit()
    return c


@router.patch("/connectors/{connector_id}", response_model=ConnectorOut)
async def patch_connector(connector_id: uuid.UUID, body: dict, request: Request, user: User = Depends(require_roles("org_admin", "workspace_admin")),
                          db: AsyncSession = Depends(get_db)):
    c = await db.get(Connector, connector_id)
    if not c:
        raise HTTPException(404, "connector not found")
    allowed = {"approved", "enabled", "team_ids", "allowed_tools", "denied_tools", "risk_class", "required_scopes", "oauth", "url", "display_name", "description"}
    if "org_admin" not in user.role_names:
        allowed = {"approved", "team_ids"}  # workspace_admin: approve for a team only
        if "team_ids" in body and body["team_ids"] and not set(uuid.UUID(t) for t in body["team_ids"]) <= user.team_ids:
            raise HTTPException(403, "workspace_admin may only approve for own teams")
    before = {k: getattr(c, k) for k in allowed if k in body and k != "oauth"}
    for k, v in body.items():
        if k in allowed:
            setattr(c, k, v)
    await record_audit(db, action="connector.updated", actor_id=user.id, entity_type="connector", entity_id=c.id, request_id=request_id(request),
                       ip=client_ip(request), before=before, after={k: v for k, v in body.items() if k in allowed and k != "oauth"})
    await db.commit()
    return c


@router.get("/roles")
async def list_roles(user: User = Depends(require_roles("org_admin")), db: AsyncSession = Depends(get_db)):
    return [r.name for r in (await db.execute(select(Role))).scalars().all()]


@router.post("/users/{user_id}/roles")
async def set_roles(user_id: uuid.UUID, body: dict, request: Request, user: User = Depends(require_roles("org_admin")), db: AsyncSession = Depends(get_db)):
    """Manual override; normally roles come from PingID group claims at login."""
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(404, "user not found")
    names = set(body.get("roles", [])) | {"user"}
    rows = (await db.execute(select(Role).where(Role.name.in_(list(names))))).scalars().all()
    before = sorted(target.role_names)
    target.roles = list(rows)
    await record_audit(db, action="user.roles_changed", actor_id=user.id, entity_type="user", entity_id=target.id, request_id=request_id(request),
                       ip=client_ip(request), before={"roles": before}, after={"roles": sorted(names)})
    await db.commit()
    return {"roles": sorted(names)}


@router.post("/users/{user_id}/status")
async def set_status(user_id: uuid.UUID, body: dict, request: Request, user: User = Depends(require_roles("org_admin")), db: AsyncSession = Depends(get_db)):
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(404, "user not found")
    status = body.get("status")
    if status not in ("active", "disabled"):
        raise HTTPException(400, "status must be active|disabled")
    await record_audit(db, action="user.status_changed", actor_id=user.id, entity_type="user", entity_id=target.id, request_id=request_id(request),
                       ip=client_ip(request), before={"status": target.status}, after={"status": status})
    target.status = status
    await db.commit()
    return {"status": status}
