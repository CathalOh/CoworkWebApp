#!/usr/bin/env bash
# Local dev without Docker for the app services (Postgres/Redis/mock still via compose).
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d postgres redis mock-iliad
export DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app REDIS_URL=redis://localhost:6379/0 \
       MODEL_PROVIDER=${MODEL_PROVIDER:-iliad_anthropic} AGENT_RUNTIME=${AGENT_RUNTIME:-agent_sdk} \
       ILIAD_BASE_URL=${ILIAD_BASE_URL:-http://localhost:9100} ILIAD_AUTH_TOKEN=${ILIAD_AUTH_TOKEN:-mock} \
       OBJECT_STORE_PATH=./data/objects WORKSPACES_ROOT=./data/workspaces
(cd backend && . .venv/bin/activate && alembic upgrade head && python -m app.seed)
(cd backend && . .venv/bin/activate && arq app.tasks.worker.WorkerSettings) &
(cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000) &
(cd frontend && npm run dev) &
wait
