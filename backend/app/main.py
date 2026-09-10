"""FastAPI application factory."""
from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import admin, artifacts, auth, connectors, conversations, extensions, health, projects, teams
from app.auth.session import SessionStore
from app.config import get_settings
from app.observability import metrics
from app.observability.logging import configure_logging, get_logger, request_id_var, run_db_log_sink
from app.security.headers import SecurityHeadersMiddleware
from app.security.ratelimit import check_rate_limit

log = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging("DEBUG" if s.debug else "INFO")
    redis = None
    if not (s.env == "test" or s.redis_url.startswith("memory://")):
        import redis.asyncio as aioredis

        redis = aioredis.from_url(s.redis_url, decode_responses=True)
    app.state.redis = redis
    app.state.sessions = SessionStore(redis)
    stop = asyncio.Event()
    sink = asyncio.create_task(run_db_log_sink(stop)) if s.env != "test" else None
    log.info("api_started", env=s.env, runtime=s.agent_runtime, provider=s.model_provider)
    try:
        yield
    finally:
        stop.set()
        if sink:
            sink.cancel()
        if redis is not None:
            await redis.aclose()


def problem(request: Request, status: int, title: str, detail: str | None = None) -> JSONResponse:
    return JSONResponse({"type": "about:blank", "title": title, "status": status, "detail": detail, "instance": str(request.url.path),
                         "request_id": getattr(request.state, "request_id", None)}, status_code=status, media_type="application/problem+json")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Cowork Backbone API", version="0.1.0", lifespan=lifespan, docs_url="/docs" if not s.is_prod else None)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=[s.frontend_origin], allow_credentials=True, allow_methods=["*"],
                       allow_headers=["*", s.csrf_header_name, "Last-Event-ID", "Idempotency-Key"], expose_headers=["X-Request-Id"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        token = request_id_var.set(rid)
        t0 = time.perf_counter()
        try:
            key = request.cookies.get(s.session_cookie_name, "")[:32] or (request.client.host if request.client else "anon")
            if not await check_rate_limit(app.state.redis, key, s.rate_limit_per_minute):
                return problem(request, 429, "Too Many Requests", "rate limit exceeded")
            resp = await call_next(request)
        finally:
            request_id_var.reset(token)
            metrics.observe("http_request_seconds", time.perf_counter() - t0, path=request.url.path.split("/")[1] if "/" in request.url.path else "")
        resp.headers["X-Request-Id"] = rid
        return resp

    @app.exception_handler(HTTPException)
    async def http_exc(request: Request, exc: HTTPException):
        return problem(request, exc.status_code, exc.detail if isinstance(exc.detail, str) else "error",
                       None if isinstance(exc.detail, str) else str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError):
        return problem(request, 422, "Validation Error", str(exc.errors()[:5]))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled_error", error=str(exc))
        return problem(request, 500, "Internal Server Error")

    for r in (health.router, auth.router, auth.users_router, teams.router, teams.ws_router, projects.router, conversations.router,
              connectors.router, artifacts.router, extensions.router, admin.router):
        app.include_router(r)
    return app


app = create_app()
