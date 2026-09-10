# Runbook: local development

## All-in Docker
`cp config/.env.example config/.env && docker compose up --build`. Backend runs migrations + seed on start.
UI http://localhost:5173 · API docs http://localhost:8000/docs · mock ILIAD http://localhost:9100.

## App services on the host, infra in Docker
`./scripts/dev.sh` (needs `backend/.venv` and `frontend/node_modules`).

## Fully in-process (no Docker at all)
Set `ENV=test DATABASE_URL=sqlite+aiosqlite:///./dev.db REDIS_URL=memory:// AGENT_RUNTIME=mock MODEL_PROVIDER=mock`.
Jobs run inline in the API process, the event bus is in-memory, and the MockRuntime scripts responses (see
`backend/app/orchestration/mock.py`). This is what the Playwright suite uses.

## Real Agent SDK against the mock ILIAD, in-process
`MODEL_PROVIDER=iliad_anthropic AGENT_RUNTIME=agent_sdk ILIAD_BASE_URL=http://localhost:9100 ILIAD_AUTH_TOKEN=mock`
with the mock server running (`cd tests/mock_iliad && uvicorn server:app --port 9100`). The SDK's bundled `claude` CLI
needs Node ≥ 18 on the PATH.

## Seeded accounts (dev-login)
admin@example.com (org_admin, developer) · lead@example.com (team_lead) · user@example.com · auditor@example.com — all in
"Demo Team". Connectors: calc + backbone (in-process), mock-drive (remote OAuth), fs-local (stdio, gated by `local_mcp`).
