# Cowork Backbone

A multi-user, single-org web re-implementation of Claude Desktop / Claude Cowork, built as a reusable **backbone** for
Cowork-style agentic knowledge-work apps. FastAPI + React (TypeScript), orchestration through the **Claude Agent SDK
(Python)** behind an `AgentRuntime` seam (LangChain Deep Agents as the swap-in fallback), every model call routed to the
enterprise gateway **ILIAD** via a `ModelProvider` seam, PingID SSO, per-user MCP connectors with server-side OAuth 2.1 +
PKCE, per-run hardened sandboxes, durable/resumable SSE runs, and DB-stored **tamper-evident audit logging**.

The full product requirements + technical design is in [`docs/PRD.md`](docs/PRD.md); what was built and how it maps to the
PRD is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Quick start (docker-compose, mock ILIAD)

```bash
cp config/.env.example config/.env          # defaults point the Agent SDK at the bundled mock ILIAD
docker compose up --build                   # postgres(pgvector) redis mock-iliad backend worker scheduler frontend
open http://localhost:5173                  # dev-login as admin@example.com / user@example.com (seeded)
```

Optional profiles: `--profile sandbox` (builds the hardened per-run sandbox image + egress allowlist proxy; set
`SANDBOX_BACKEND=docker`), `--profile litellm` (OpenAI-compatible fallback gateway for the Deep Agents path).

## Quick start (no Docker)

```bash
cd backend && uv venv .venv && . .venv/bin/activate && uv pip install -e ".[dev]"
cd ../frontend && npm install
cd .. && ./scripts/dev.sh                   # starts postgres/redis/mock via compose, then api + worker + vite
```

Fully in-process dev/test (sqlite + in-memory bus + inline worker + mock runtime): see `tests/e2e/README.md`.

## Point it at the real ILIAD (Decision Gate A)

```bash
ILIAD_BASE_URL=https://iliad.internal ILIAD_AUTH_TOKEN=... CLAUDE_AGENT_MODEL=<exact-id> \
  backend/.venv/bin/python scripts/iliad_spike.py      # writes docs/spike-results.json, exit 0 = PASS
```

PASS → keep `MODEL_PROVIDER=iliad_anthropic AGENT_RUNTIME=agent_sdk`. FAIL → `MODEL_PROVIDER=iliad_openai_compat
AGENT_RUNTIME=deep_agents` plus `--profile litellm`; nothing else changes (see ADR-001/002).

## Repository layout

```
backend/            FastAPI app: api/ auth/ orchestration/ providers/ mcp_host/ sandbox/ tasks/ scheduler/ models/
                    schemas/ migrations/ services/ security/ observability/ + tests/
frontend/           React + TypeScript SPA (Vite): features/ lib/{api,sse,markdown,oidc} components/ slots/ store/
sandbox-runner/     hardened per-session container image
tests/mock_iliad/   mock ILIAD (Anthropic Messages API) + mock remote MCP server + OAuth AS + mock OIDC (PingID stand-in)
tests/e2e/          Playwright end-to-end suite
config/             .env.example, seccomp profile, egress proxy config, LiteLLM config
scripts/            iliad_spike.py (Decision Gate A), dev.sh
docs/               PRD, ARCHITECTURE, ADRs, runbooks, ILIAD/PingID question lists
docker-compose.yml
```

## Tests

```bash
cd backend && . .venv/bin/activate && ruff check app tests && pytest             # sqlite, in-memory bus, mock runtime
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app pytest          # real Postgres via Alembic (partitions, triggers, pgvector)
cd frontend && npm run typecheck && npm run build
cd tests/mock_iliad && pytest
cd tests/e2e && npm install && npx playwright test
```

## Roles (from PingID group claims, see `ROLE_GROUP_MAP_JSON`)

`user`, `team_lead`, `workspace_admin`, `org_admin`, `auditor` (read-only logs), `developer` (tools/skills/plugins/bundles).
