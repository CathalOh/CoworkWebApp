from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.observability.metrics import render_prometheus
from app.providers.iliad import get_model_provider
from app.sandbox.runner import get_sandbox_runner

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz():
    return {"ok": True}


@router.get("/readyz")
async def readyz(response: Response, db: AsyncSession = Depends(get_db)):
    s = get_settings()
    checks: dict[str, dict] = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = {"ok": True}
    except Exception as exc:
        checks["postgres"] = {"ok": False, "error": str(exc)}
    try:
        if s.redis_url.startswith("memory://") or s.env == "test":
            checks["redis"] = {"ok": True, "mode": "memory"}
        else:
            import redis.asyncio as aioredis

            r = aioredis.from_url(s.redis_url)
            await r.ping()
            await r.aclose()
            checks["redis"] = {"ok": True}
    except Exception as exc:
        checks["redis"] = {"ok": False, "error": str(exc)}
    ok, msg = await get_model_provider().healthcheck()
    checks["model_provider"] = {"ok": ok, "detail": msg, "provider": s.model_provider, "runtime": s.agent_runtime}
    checks["sandbox"] = await get_sandbox_runner().health()
    ready = checks["postgres"]["ok"] and checks["redis"]["ok"]
    response.status_code = 200 if ready else 503
    return {"ready": ready, "checks": checks}


@router.get("/metrics")
async def metrics():
    return Response(render_prometheus(), media_type="text/plain; version=0.0.4")


@router.get("/v1/meta")
async def meta():
    s = get_settings()
    return {"app": s.app_name, "env": s.env, "runtime": s.agent_runtime, "provider": s.model_provider, "model": s.claude_agent_model,
            "dev_login": s.dev_login_enabled, "oidc": bool(s.oidc_issuer), "sandbox": s.sandbox_backend,
            "capabilities": get_model_provider().capabilities().__dict__}
