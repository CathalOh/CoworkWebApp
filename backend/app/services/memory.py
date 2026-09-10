"""Memory + semantic search over pgvector (HNSW/cosine in Postgres; brute-force cosine elsewhere).

Scope rules mirror Cowork: memories are per user and per project, never a global personal store; a project
can opt out (memory_enabled=false) and shares memory with a team only when the ACL row says so.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Embedding, Memory, Message, Project
from app.services.embeddings import cosine, embed


async def embed_pending_messages(db: AsyncSession, conversation_id: uuid.UUID) -> int:
    conv = await db.get(Conversation, conversation_id)
    if conv is None:
        return 0
    if conv.project_id:
        proj = await db.get(Project, conv.project_id)
        if proj and not proj.memory_enabled:
            return 0
    msgs = (await db.execute(select(Message).where(Message.conversation_id == conversation_id, Message.embedding_id.is_(None),
                                                   Message.text_cache.isnot(None)))).scalars().all()
    msgs = [m for m in msgs if (m.text_cache or "").strip()]
    if not msgs:
        return 0
    vecs = await embed([m.text_cache or "" for m in msgs])
    for m, v in zip(msgs, vecs, strict=True):
        e = Embedding(ref_type="message", ref_id=m.id, user_id=conv.user_id, project_id=conv.project_id, embedding=v)
        db.add(e)
        await db.flush()
        m.embedding_id = e.id
    return len(msgs)


async def add_memory(db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID | None, content: str, memory_type: str = "fact",
                     source_message_id: uuid.UUID | None = None) -> Memory:
    m = Memory(user_id=user_id, project_id=project_id, content=content, memory_type=memory_type, source_message_id=source_message_id)
    db.add(m)
    await db.flush()
    (vec,) = await embed([content])
    db.add(Embedding(ref_type="memory", ref_id=m.id, user_id=user_id, project_id=project_id, embedding=vec))
    return m


async def generate_memories_from_conversation(db: AsyncSession, conversation_id: uuid.UUID, max_items: int = 5) -> list[Memory]:
    """Heuristic extractor (no model call): pulls user statements that look like durable facts/preferences.
    Swap for a model-backed summarizer once the provider is live; the storage path is identical."""
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        return []
    if conv.project_id:
        proj = await db.get(Project, conv.project_id)
        if proj and not proj.memory_enabled:
            return []
    msgs = (await db.execute(select(Message).where(Message.conversation_id == conversation_id, Message.role == "user")
                             .order_by(Message.seq))).scalars().all()
    out: list[Memory] = []
    markers = ("i prefer", "always", "never", "my name is", "we use", "our team", "remember that", "i like", "i work")
    for m in msgs:
        t = (m.text_cache or "").strip()
        low = t.lower()
        if any(k in low for k in markers) and 10 < len(t) < 400:
            out.append(await add_memory(db, conv.user_id, conv.project_id, t, "preference" if "prefer" in low or "like" in low else "fact", m.id))
            if len(out) >= max_items:
                break
    return out


async def semantic_search(db: AsyncSession, user_id: uuid.UUID, query: str, project_ids: list[uuid.UUID] | None = None,
                          ref_types: tuple[str, ...] = ("message", "memory"), limit: int = 10) -> list[dict[str, Any]]:
    (qv,) = await embed([query])
    dialect = db.bind.dialect.name if db.bind is not None else "sqlite"
    if dialect == "postgresql":
        proj_clause = "AND (project_id = ANY(:pids))" if project_ids else ""
        rows = (await db.execute(text(f"""
            SELECT id, ref_type, ref_id, project_id, 1 - (embedding <=> CAST(:q AS vector)) AS score
            FROM embeddings WHERE user_id = :uid AND ref_type = ANY(:types) {proj_clause}
            ORDER BY embedding <=> CAST(:q AS vector) LIMIT :lim"""),
            {"q": str(qv), "uid": user_id, "types": list(ref_types), "pids": project_ids or [], "lim": limit})).mappings().all()
        return [dict(r) for r in rows]
    q = select(Embedding).where(Embedding.user_id == user_id, Embedding.ref_type.in_(ref_types))
    if project_ids:
        q = q.where(Embedding.project_id.in_(project_ids))
    rows = (await db.execute(q)).scalars().all()
    scored = sorted(((cosine(qv, list(e.embedding)), e) for e in rows), key=lambda x: -x[0])[:limit]
    return [{"id": e.id, "ref_type": e.ref_type, "ref_id": e.ref_id, "project_id": e.project_id, "score": s} for s, e in scored]


async def relevant_memories(db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID | None, query: str, limit: int = 5) -> list[Memory]:
    hits = await semantic_search(db, user_id, query, [project_id] if project_id else None, ("memory",), limit)
    ids = [h["ref_id"] for h in hits if h["score"] > 0.15]
    if not ids:
        return []
    rows = (await db.execute(select(Memory).where(Memory.id.in_(ids)))).scalars().all()
    order = {i: n for n, i in enumerate(ids)}
    return sorted(rows, key=lambda m: order.get(m.id, 99))
