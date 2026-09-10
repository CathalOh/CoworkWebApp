"""Skills, plugins, memory, search, tasks, schedules, bundles."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import client_ip, current_user, is_admin, request_id, require_roles
from app.db import get_db
from app.models import Conversation, Memory, Message, Plugin, ProjectBundle, Schedule, Skill, Task, User
from app.scheduler.service import compute_next, run_task_now, validate_cron
from app.schemas.extensions import (
    BundleIn,
    BundleOut,
    MemoryIn,
    MemoryOut,
    PluginIn,
    PluginOut,
    ScheduleIn,
    ScheduleOut,
    SkillIn,
    SkillOut,
    TaskIn,
    TaskOut,
)
from app.security.audit import record_audit
from app.services import skills as skills_svc
from app.services.memory import add_memory, semantic_search
from app.services.runs import RunRejected

router = APIRouter(prefix="/v1", tags=["extensions"])


# ---- skills --------------------------------------------------------------------------------------
@router.get("/skills", response_model=list[SkillOut])
async def list_skills(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await skills_svc.visible_skills(db, user)


@router.post("/skills", response_model=SkillOut, status_code=201)
async def create_skill(body: SkillIn, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if body.scope == "org" and not (is_admin(user) or "developer" in user.role_names):
        raise HTTPException(403, "org-scoped skills require developer or org_admin")
    if body.scope == "team" and (not body.team_id or (body.team_id not in user.team_ids and not is_admin(user))):
        raise HTTPException(403, "team-scoped skills require team membership")
    sk = Skill(owner_id=user.id, **body.model_dump())
    db.add(sk)
    await db.flush()
    await record_audit(db, action="skill.created", actor_id=user.id, entity_type="skill", entity_id=sk.id, request_id=request_id(request),
                       ip=client_ip(request), after={"name": sk.name, "scope": sk.scope, "allowed_tools": sk.allowed_tools})
    await db.commit()
    return sk


@router.post("/skills/import", response_model=SkillOut, status_code=201)
async def import_skill_md(body: dict, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    parsed = skills_svc.parse_skill_md(str(body.get("skill_md", "")))
    if not parsed.get("name"):
        raise HTTPException(400, "SKILL.md must have a name in frontmatter")
    return await create_skill(SkillIn(name=parsed["name"], description=parsed["description"], body=parsed["body"],
                                      allowed_tools=parsed["allowed_tools"], scope=body.get("scope", "user"),
                                      team_id=body.get("team_id")), request, user, db)


@router.put("/skills/{skill_id}", response_model=SkillOut)
async def update_skill(skill_id: uuid.UUID, body: SkillIn, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    sk = await db.get(Skill, skill_id)
    if not sk or (sk.owner_id != user.id and not is_admin(user)):
        raise HTTPException(404, "skill not found")
    for k, v in body.model_dump().items():
        setattr(sk, k, v)
    await record_audit(db, action="skill.updated", actor_id=user.id, entity_type="skill", entity_id=sk.id, request_id=request_id(request), ip=client_ip(request))
    await db.commit()
    return sk


@router.delete("/skills/{skill_id}", status_code=204)
async def delete_skill(skill_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    sk = await db.get(Skill, skill_id)
    if not sk or (sk.owner_id != user.id and not is_admin(user)):
        raise HTTPException(404, "skill not found")
    await record_audit(db, action="skill.deleted", actor_id=user.id, entity_type="skill", entity_id=sk.id, request_id=request_id(request),
                       ip=client_ip(request), before={"name": sk.name})
    await db.delete(sk)
    await db.commit()


# ---- plugins -------------------------------------------------------------------------------------
@router.get("/plugins", response_model=list[PluginOut])
async def list_plugins(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    q = select(Plugin)
    if not is_admin(user):
        q = q.where(or_(Plugin.team_id.is_(None), Plugin.team_id.in_(list(user.team_ids) or [uuid.uuid4()])))
    return (await db.execute(q.order_by(Plugin.name))).scalars().all()


@router.post("/plugins", response_model=PluginOut, status_code=201)
async def create_plugin(body: PluginIn, request: Request, user: User = Depends(require_roles("developer", "org_admin")), db: AsyncSession = Depends(get_db)):
    data = body.model_dump()
    if not is_admin(user):
        data["approved"] = False  # org_admin approves third-party bundles (supply-chain review)
    p = Plugin(**data)
    db.add(p)
    await db.flush()
    await record_audit(db, action="plugin.registered", actor_id=user.id, entity_type="plugin", entity_id=p.id, request_id=request_id(request),
                       ip=client_ip(request), after={"name": p.name, "version": p.version, "approved": p.approved})
    await db.commit()
    return p


@router.patch("/plugins/{plugin_id}", response_model=PluginOut)
async def patch_plugin(plugin_id: uuid.UUID, body: dict, request: Request, user: User = Depends(require_roles("org_admin")), db: AsyncSession = Depends(get_db)):
    p = await db.get(Plugin, plugin_id)
    if not p:
        raise HTTPException(404, "plugin not found")
    for k in ("approved", "enabled", "manifest", "version"):
        if k in body:
            setattr(p, k, body[k])
    await record_audit(db, action="plugin.updated", actor_id=user.id, entity_type="plugin", entity_id=p.id, request_id=request_id(request),
                       ip=client_ip(request), after={k: body[k] for k in body if k != "manifest"})
    await db.commit()
    return p


# ---- memory --------------------------------------------------------------------------------------
@router.get("/memory", response_model=list[MemoryOut])
async def list_memory(project_id: uuid.UUID | None = None, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    q = select(Memory).where(Memory.user_id == user.id)
    if project_id:
        q = q.where(Memory.project_id == project_id)
    return (await db.execute(q.order_by(Memory.created_at.desc()).limit(500))).scalars().all()


@router.post("/memory", response_model=MemoryOut, status_code=201)
async def create_memory(body: MemoryIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    m = await add_memory(db, user.id, body.project_id, body.content, body.memory_type)
    await db.commit()
    return m


@router.delete("/memory/{memory_id}", status_code=204)
async def delete_memory(memory_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    m = await db.get(Memory, memory_id)
    if not m or m.user_id != user.id:
        raise HTTPException(404, "memory not found")
    await record_audit(db, action="memory.deleted", actor_id=user.id, entity_type="memory", entity_id=m.id, request_id=request_id(request), ip=client_ip(request))
    await db.delete(m)
    await db.commit()


# ---- search --------------------------------------------------------------------------------------
@router.get("/search")
async def search(q: str, limit: int = 20, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Hybrid: semantic (pgvector) + substring/full-text over the user's own conversations."""
    q = q.strip()
    if not q:
        return {"items": []}
    sem = await semantic_search(db, user.id, q, None, ("message", "memory"), limit)
    msg_ids = [h["ref_id"] for h in sem if h["ref_type"] == "message"]
    score = {h["ref_id"]: h["score"] for h in sem}
    lexical = (await db.execute(select(Message).join(Conversation, Conversation.id == Message.conversation_id)
                                .where(Conversation.user_id == user.id, Message.text_cache.ilike(f"%{q}%"))
                                .order_by(Message.created_at.desc()).limit(limit))).scalars().all()
    ids = list(dict.fromkeys(msg_ids + [m.id for m in lexical]))
    if not ids:
        return {"items": []}
    rows = (await db.execute(select(Message, Conversation.title).join(Conversation, Conversation.id == Message.conversation_id)
                             .where(Message.id.in_(ids), Conversation.user_id == user.id))).all()
    items = [{"message_id": m.id, "conversation_id": m.conversation_id, "title": title, "role": m.role,
              "snippet": (m.text_cache or "")[:300], "score": score.get(m.id, 0.0), "created_at": m.created_at} for m, title in rows]
    items.sort(key=lambda x: (-x["score"], x["created_at"]), reverse=False)
    return {"items": items[:limit]}


# ---- tasks & schedules ---------------------------------------------------------------------------
@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Task).where(Task.owner_id == user.id).order_by(Task.created_at.desc()))).scalars().all()


@router.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(body: TaskIn, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if body.config.get("permission_mode") == "bypassPermissions":
        raise HTTPException(400, "bypassPermissions is not allowed")
    t = Task(owner_id=user.id, name=body.name, prompt=body.prompt, config=body.config)
    db.add(t)
    await db.flush()
    await record_audit(db, action="task.created", actor_id=user.id, entity_type="task", entity_id=t.id, request_id=request_id(request), ip=client_ip(request),
                       after={"name": t.name})
    await db.commit()
    return t


@router.put("/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: uuid.UUID, body: TaskIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    t = await db.get(Task, task_id)
    if not t or t.owner_id != user.id:
        raise HTTPException(404, "task not found")
    t.name, t.prompt, t.config = body.name, body.prompt, body.config
    await db.commit()
    return t


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    t = await db.get(Task, task_id)
    if not t or t.owner_id != user.id:
        raise HTTPException(404, "task not found")
    await db.delete(t)
    await db.commit()


@router.post("/tasks/{task_id}/run", status_code=202)
async def run_task(task_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    t = await db.get(Task, task_id)
    if not t or t.owner_id != user.id:
        raise HTTPException(404, "task not found")
    try:
        run_id = await run_task_now(db, t, user)
    except RunRejected as exc:
        raise HTTPException(exc.status, exc.reason) from exc
    await db.commit()
    from app.tasks.queue import enqueue

    await enqueue("execute_run", run_id)
    return {"run_id": run_id}


@router.get("/tasks/{task_id}/runs")
async def task_runs(task_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    from app.models import Run
    from app.schemas.chat import RunOut

    t = await db.get(Task, task_id)
    if not t or t.owner_id != user.id:
        raise HTTPException(404, "task not found")
    rows = (await db.execute(select(Run).where(Run.task_id == task_id).order_by(Run.created_at.desc()).limit(50))).scalars().all()
    return [RunOut.model_validate(r) for r in rows]


@router.get("/schedules", response_model=list[ScheduleOut])
async def list_schedules(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Schedule).join(Task, Task.id == Schedule.task_id).where(Task.owner_id == user.id))).scalars().all()


@router.post("/schedules", response_model=ScheduleOut, status_code=201)
async def create_schedule(body: ScheduleIn, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    t = await db.get(Task, body.task_id)
    if not t or t.owner_id != user.id:
        raise HTTPException(404, "task not found")
    if not validate_cron(body.cron):
        raise HTTPException(400, "invalid cron expression")
    try:
        nxt = compute_next(body.cron, body.timezone)
    except Exception as exc:
        raise HTTPException(400, f"invalid timezone or cron: {exc}") from exc
    s = Schedule(task_id=t.id, cron=body.cron, timezone=body.timezone, permission_mode=body.permission_mode, enabled=body.enabled, next_run=nxt)
    db.add(s)
    await db.flush()
    await record_audit(db, action="schedule.created", actor_id=user.id, entity_type="schedule", entity_id=s.id, request_id=request_id(request),
                       ip=client_ip(request), after={"cron": s.cron, "permission_mode": s.permission_mode})
    await db.commit()
    return s


@router.patch("/schedules/{schedule_id}", response_model=ScheduleOut)
async def patch_schedule(schedule_id: uuid.UUID, body: dict, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    s = await db.get(Schedule, schedule_id)
    t = await db.get(Task, s.task_id) if s else None
    if not s or not t or t.owner_id != user.id:
        raise HTTPException(404, "schedule not found")
    if "cron" in body:
        if not validate_cron(body["cron"]):
            raise HTTPException(400, "invalid cron expression")
        s.cron = body["cron"]
    if "timezone" in body:
        s.timezone = body["timezone"]
    if "enabled" in body:
        s.enabled = bool(body["enabled"])
    if "permission_mode" in body and body["permission_mode"] != "bypassPermissions":
        s.permission_mode = body["permission_mode"]
    s.next_run = compute_next(s.cron, s.timezone)
    await db.commit()
    return s


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    s = await db.get(Schedule, schedule_id)
    t = await db.get(Task, s.task_id) if s else None
    if not s or not t or t.owner_id != user.id:
        raise HTTPException(404, "schedule not found")
    await db.delete(s)
    await db.commit()


# ---- project bundles (cowork-project manifests) ---------------------------------------------------
@router.get("/bundles", response_model=list[BundleOut])
async def list_bundles(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(ProjectBundle).where(ProjectBundle.enabled.is_(True)).order_by(ProjectBundle.name))).scalars().all()


@router.post("/bundles", response_model=BundleOut, status_code=201)
async def create_bundle(body: BundleIn, request: Request, user: User = Depends(require_roles("developer", "org_admin")), db: AsyncSession = Depends(get_db)):
    b = ProjectBundle(owner_id=user.id, **body.model_dump())
    db.add(b)
    await db.flush()
    await record_audit(db, action="bundle.created", actor_id=user.id, entity_type="bundle", entity_id=b.id, request_id=request_id(request),
                       ip=client_ip(request), after={"name": b.name})
    await db.commit()
    return b


@router.put("/bundles/{bundle_id}", response_model=BundleOut)
async def update_bundle(bundle_id: uuid.UUID, body: BundleIn, user: User = Depends(require_roles("developer", "org_admin")), db: AsyncSession = Depends(get_db)):
    b = await db.get(ProjectBundle, bundle_id)
    if not b:
        raise HTTPException(404, "bundle not found")
    b.name, b.manifest, b.enabled = body.name, body.manifest, body.enabled
    await db.commit()
    return b
