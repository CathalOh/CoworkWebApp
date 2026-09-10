# Architecture — what was built, mapped to the PRD

## Services (docker-compose)

| Service | Image | Role |
|---|---|---|
| `postgres` | pgvector/pgvector:pg16 | domain tables, partitioned append-only log tables, HNSW embeddings |
| `redis` | redis:7 | arq broker, Redis Streams per run (offset-resumable events), control channel, sessions, rate limits |
| `backend` | backend/Dockerfile | FastAPI gateway: auth (OIDC BFF), REST, SSE, WS; runs `alembic upgrade head` + seed on start |
| `worker` | same image | arq worker: `execute_run` (RunHost + AgentRuntime), embeddings/memory, schedule firing, retention |
| `scheduler` | same image | cron loop → enqueues due schedules (worker also runs a cron fallback) |
| `mock-iliad` | tests/mock_iliad | Anthropic Messages API mock + remote MCP + OAuth AS + OIDC mock |
| `frontend` | frontend/Dockerfile | nginx serving the SPA, proxying `/v1` (SSE/WS friendly) |
| `sandbox-image`, `egress-proxy` | profile `sandbox` | hardened per-run containers + tinyproxy allowlist |
| `litellm` | profile `litellm` | OpenAI-compatible fallback gateway |

## Seams (PRD §7.1, §7.2)

* `app/orchestration/base.py` — `RunConfig`, `AgentEvent`, `AgentRuntime` protocol, `RuntimeHooks` (approval /
  elicitation / emit / interrupt bridge). Nothing outside `orchestration/` imports an SDK.
* `app/orchestration/agent_sdk.py` — `AgentSdkRuntime` over `ClaudeSDKClient` (`setting_sources=[]`,
  `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, `can_use_tool` + PreToolUse/PostToolUse hooks, in-process MCP servers via
  `create_sdk_mcp_server`, sub-agents via `AgentDefinition`, skills dirs, local plugins, `max_budget_usd`, `task_budget`,
  `get_mcp_status()` → `mcp_status` events, `ResultMessage` → cost/usage).
* `app/orchestration/deep_agents.py` — `DeepAgentsRuntime` over `create_deep_agent` (LangGraph interrupts → the same
  approval flow, MCP tools through `langchain-mcp-adapters`, `mcp__<server>__<tool>` naming preserved).
* `app/orchestration/mock.py` — deterministic scripted runtime for tests/e2e and the walking skeleton.
* `app/providers/iliad.py` — `IliadAnthropicProvider` (`ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN`/
  `ANTHROPIC_CUSTOM_HEADERS`/`CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`/`NODE_EXTRA_CA_CERTS`), `IliadOpenAICompatProvider`
  (LiteLLM), `MockProvider`; `Capabilities` recorded by `scripts/iliad_spike.py`.

## Run lifecycle (PRD §5.2, §7.5, §7.6)

1. `POST /v1/conversations/{id}/messages` → `services.runs.start_run` (kill-switch, per-user concurrency, cost quota,
   `bypassPermissions` forbidden) → `Run(queued)` + user `Message` → audit `run.created` → commit → `enqueue(execute_run)`.
2. Worker `execute_run` → `services.run_builder.build_run_config` (system prompt pack, project instructions + files copied
   into the workspace, pgvector memories, SKILL.md materialized under `.claude/skills`, connectors with per-user Bearer
   tokens, plugins materialized, sub-agent definitions, provider env, budgets; **context manifest** stored on the run).
3. `RunHost.execute` → sandbox `start` → `runtime.run(cfg, host)`. Every event gets a monotonic `seq`, is XADDed to
   `run:{id}:events` (Redis Streams, id = `seq-0`) and batched into `run_events` (durable copy).
4. `GET /v1/runs/{id}/events` (SSE) replays `run_events` after `Last-Event-ID`, then follows the stream. No duplicates,
   no model rework; the run continues whether or not a client is attached (durable session).
5. Approvals/elicitations: `RunHost.request_approval` persists an `approvals` row, emits `approval_request`, and awaits a
   control message (`POST /v1/runs/{id}/approvals` or the WS) with a timeout → deny. Decisions are audit-logged.
6. Finalize: assistant `Message` + `content_blocks` + `tool_calls`/`tool_results`, `usage_records`, `llm_request_logs`,
   run status/cost, audit `run.<status>`, then `embed_conversation` job (pgvector + heuristic memory extraction).

## Permission model (PRD §10)

`app/orchestration/policy.py` evaluates every tool call in this order: secret-path / workspace-escape / kill-switch /
deny-list hard denies (held in **every** mode via PreToolUse) → **deletion always asks** → session always-allow →
mode (`plan` read-only, `acceptEdits`, `dontAsk`, `auto` screening, `default` asks) → allow-list. `RunConfig.tools` is
what the model can see; `RunConfig.allowed_tools` is only the pre-approved subset (read-only tools + connector
patterns), so mutating built-ins always pass through the host. Tool results are sanitized (`sanitize_tool_result`)
and injection-like content is flagged to the model as untrusted.

## MCP host (PRD §7.3)

`app/mcp_host/oauth.py` runs OAuth 2.1 + PKCE server-side (RFC 9728 → RFC 8414 discovery, RFC 7591 DCR, RFC 8707
`resource`, refresh rotation). `app/mcp_host/registry.py` stores tokens with envelope encryption (`security/crypto.py`)
and builds `McpServerConfig` dicts, injecting `Authorization: Bearer …`; connectors without a usable token surface as
`needs-auth` in the run's context manifest and the UI, and the run continues without them. Local stdio servers are gated
by the `local_mcp` org toggle and run inside the sandbox.

## Audit (PRD §8, §10)

`security/audit.py`: `record_audit` appends HMAC-SHA256-chained rows (chain per monthly `stream_key`, serialized by a
Postgres advisory lock), always inside the same transaction as the privileged mutation. Migration `0001` creates the
three log tables RANGE-partitioned by `ts` (monthly partitions via `ensure_log_partitions()`), a `BEFORE UPDATE OR DELETE`
trigger that raises, and `REVOKE UPDATE, DELETE` from `app_role`. `GET /v1/admin/audit/verify` recomputes the chain;
`/v1/admin/audit/export` streams JSONL for compliance tooling; `audit_chain_anchors` is the external-WORM anchoring target.

## Parity checklist status

Chat + streaming ✅ · Projects (+files, instructions, memory scope, sharing) ✅ · Artifacts (sandboxed srcdoc iframe,
own CSP, versions, ≤20 MB, Live refresh) ✅ · Memory (pgvector, per user/project, opt-out) ✅ · MCP (remote OAuth +
gated local stdio + in-process SDK servers) ✅ · Sandboxed workspaces (Docker hardening, egress allowlist; runner is
runtime-agnostic for gVisor/Kata/Firecracker) ✅ · Long-running/durable runs ✅ · Scheduled tasks (isolated session per
fire) ✅ · Skills (SKILL.md registry, on-demand) ✅ · Plugins (manifest → local plugin dir) ✅ · Sub-agents
(`AgentDefinition`) ✅ · Permissions (Manual/Auto/Skip + deletion protection) ✅ · Team sharing ✅ · Search (semantic +
lexical) ✅ · Admin console + kill-switches + RBAC ✅ · Audit viewer + chain verify + export ✅ · Usage/cost ✅.

## Known limitations / next steps

* Elicitation: the Python SDK hook union has no Elicitation variant yet; the host implements the UI + control channel, and
  `AgentSdkRuntime` will wire it when the package exposes it. Deep Agents path can call `request_elicitation` directly.
* Memory extraction is heuristic (no model call) — swap `generate_memories_from_conversation` for a model-backed
  summarizer once ILIAD is live; storage/search paths are unchanged.
* Embeddings default to a deterministic hashing embedder (`EMBEDDING_PROVIDER=hash`); switch to `openai_compat`.
* File uploads are type/size validated; wire an AV scanner into `Attachment.scan_status`.
* Sandbox v1 is hardened Docker; move to gVisor/Kata/Firecracker before serving untrusted org groups (ADR-005).
