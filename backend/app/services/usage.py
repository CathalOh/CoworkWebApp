from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UsageRecord
from app.models.base import utcnow


async def spend_for_user(db: AsyncSession, user_id: uuid.UUID, since: datetime | None = None) -> float:
    since = since or (utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0))
    v = (await db.execute(select(func.coalesce(func.sum(UsageRecord.cost_usd), 0)).where(UsageRecord.user_id == user_id,
                                                                                         UsageRecord.ts >= since))).scalar_one()
    return float(v or 0)


async def usage_summary(db: AsyncSession, group_by: str = "user", days: int = 30) -> list[dict]:
    col = {"user": UsageRecord.user_id, "team": UsageRecord.team_id, "project": UsageRecord.project_id, "model": UsageRecord.model_id}[group_by]
    since = utcnow() - timedelta(days=days)
    rows = (await db.execute(select(col.label("key"), func.count(UsageRecord.id), func.sum(UsageRecord.input_tokens),
                                    func.sum(UsageRecord.output_tokens), func.sum(UsageRecord.cache_read),
                                    func.sum(UsageRecord.cost_usd)).where(UsageRecord.ts >= since).group_by(col))).all()
    return [{"key": str(r[0]) if r[0] is not None else None, "runs": r[1], "input_tokens": int(r[2] or 0),
             "output_tokens": int(r[3] or 0), "cache_read": int(r[4] or 0), "cost_usd": float(r[5] or 0)} for r in rows]
