"""Structured JSON logging to stdout plus a buffered sink into app_logs. request_id propagates via contextvars."""
from __future__ import annotations

import asyncio
import contextvars
import logging
import sys
from typing import Any

import structlog

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("run_id", default=None)

_db_sink_queue: asyncio.Queue | None = None


def _add_context(logger, method, event_dict):
    rid = request_id_var.get()
    if rid:
        event_dict.setdefault("request_id", rid)
    run_id = run_id_var.get()
    if run_id:
        event_dict.setdefault("run_id", run_id)
    return event_dict


def _db_sink(logger, method, event_dict):
    """Fan a copy of the event to the DB sink queue (best effort, never blocks the caller)."""
    q = _db_sink_queue
    if q is not None:
        try:
            q.put_nowait(dict(event_dict))
        except asyncio.QueueFull:
            pass
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            _add_context,
            _db_sink,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str = "app") -> Any:
    return structlog.get_logger(name)


async def run_db_log_sink(stop: asyncio.Event) -> None:
    """Background task: drain the queue into app_logs in small batches."""
    global _db_sink_queue
    from app.db import db_session
    from app.models.logs import AppLog

    _db_sink_queue = asyncio.Queue(maxsize=5000)
    q = _db_sink_queue
    try:
        while not stop.is_set():
            try:
                first = await asyncio.wait_for(q.get(), timeout=1.0)
            except TimeoutError:
                continue
            batch = [first]
            while not q.empty() and len(batch) < 200:
                batch.append(q.get_nowait())
            try:
                async with db_session() as db:
                    for ev in batch:
                        msg = str(ev.get("event", ""))
                        ctx = {k: v for k, v in ev.items() if k not in ("event", "level", "ts", "logger", "request_id")}
                        db.add(AppLog(level=str(ev.get("level", "info")), logger=str(ev.get("logger", "app")),
                                      message=msg[:4000], context=_jsonable(ctx), request_id=ev.get("request_id")))
                    await db.commit()
            except Exception:  # pragma: no cover - sink must never crash the app
                pass
    finally:
        _db_sink_queue = None


def _jsonable(obj: Any) -> Any:
    import json

    try:
        json.dumps(obj)
        return obj
    except Exception:
        return json.loads(json.dumps(obj, default=str))
