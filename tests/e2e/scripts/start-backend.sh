#!/usr/bin/env bash
# Prepares a fresh sqlite database (schema + seed) and starts the FastAPI backend in-process test mode
# (no Postgres/Redis, MockRuntime, inline job execution). Used by playwright.config.ts as a webServer.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT/backend"

DB_PATH="${E2E_DB_PATH:-/tmp/e2e.db}"
PORT="${E2E_BACKEND_PORT:-8000}"

# Start from a clean slate so audit chains, capability flags, etc. are deterministic between runs.
rm -f "$DB_PATH" "$DB_PATH-journal" "$DB_PATH-wal" "$DB_PATH-shm"
mkdir -p "${WORKSPACES_ROOT:-/tmp/e2e-ws}" "${OBJECT_STORE_PATH:-/tmp/e2e-obj}"

export ENV=test
export DATABASE_URL="sqlite+aiosqlite:///${DB_PATH}"
export REDIS_URL="memory://"
export AGENT_RUNTIME=mock
export MODEL_PROVIDER=mock
export AUTH_DEV_BYPASS=true
export SANDBOX_BACKEND=none
export WORKSPACES_ROOT="${WORKSPACES_ROOT:-/tmp/e2e-ws}"
export OBJECT_STORE_PATH="${OBJECT_STORE_PATH:-/tmp/e2e-obj}"
export APPROVAL_TIMEOUT_SECONDS="${APPROVAL_TIMEOUT_SECONDS:-120}"
export FRONTEND_ORIGIN="${FRONTEND_ORIGIN:-http://localhost:5173}"
# The suite fires many requests from one client; keep the per-session rate limiter out of the way.
export RATE_LIMIT_PER_MINUTE="${RATE_LIMIT_PER_MINUTE:-100000}"
# Several specs keep an approval pending while another run streams; lift the per-user cap a little.
export MAX_CONCURRENT_RUNS_PER_USER="${MAX_CONCURRENT_RUNS_PER_USER:-8}"

# ENV=test does not auto-create the schema: create it and seed the demo data.
.venv/bin/python - <<'PY'
import asyncio
from app.db import get_engine
from app.models import Base
from app.seed import seed

async def main():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed()

asyncio.run(main())
PY

exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
