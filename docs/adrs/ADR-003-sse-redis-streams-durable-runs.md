# ADR-003: SSE + Redis Streams for offset-resumable durable runs; WebSocket only for approvals/steering

**Status:** accepted · **Date:** 2026-09-10

## Decision
Workers publish every `AgentEvent` with a monotonic `seq` to a Redis Stream keyed by run (entry id `seq-0`) and batch
them into `run_events`. `GET /v1/runs/{id}/events` replays the DB after `Last-Event-ID` then follows the stream; a
reconnecting client gets exactly the events after its last offset. The run never depends on a client being connected.
A WebSocket (`/v1/runs/{id}/ws`) multiplexes the same events with approval/elicitation/interrupt messages upstream; the
REST endpoints for those exist too, so the UI works with SSE alone.

## Consequences
"Close the laptop, it keeps going" works by construction. Stream retention is `EVENT_RETENTION_SECONDS`; older resumes
are served from `run_events` (7-day retention sweep). In test/dev with `REDIS_URL=memory://` an in-memory bus is used.
