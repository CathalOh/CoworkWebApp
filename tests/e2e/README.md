# End-to-end tests (Playwright)

Drives the real SPA (Vite dev server on :5173) against the real FastAPI backend running in fully in-process test mode
(sqlite, in-memory event bus, inline jobs, deterministic `MockRuntime`) on :8000. No Docker, Postgres or Redis needed.

```bash
cd tests/e2e && npm install && npx playwright test          # boots both servers via playwright.config.ts webServer
npx playwright show-report report                           # HTML report
```

Chromium must be installed for Playwright (`npx playwright install chromium`, or set `E2E_CHROMIUM_PATH`).

Against an already running stack (e.g. `docker compose up`): `E2E_BASE_URL=http://localhost:5173 npx playwright test`
(no servers are started; the stack must use `AGENT_RUNTIME=mock` for the scripted prompts to behave, and dev-login must
be enabled).

## Specs

| Spec | Covers |
|---|---|
| `login.spec.ts` | dev login form, sign out, protected-route redirect |
| `chat.spec.ts` | new conversation, streamed reply, cost chip, **reload survival / stream resume** of an in-flight run |
| `approvals.spec.ts` | Write needs approval in default mode (Allow), deletion protection in acceptEdits (Deny, no "always allow"), Stop/interrupt |
| `admin.spec.ts` | audit viewer filters (tool.approval_requested / tool.approved rows), chain verification, `new_runs` kill-switch drains runs (503 + UI toast), re-enable |
| `projects.spec.ts` | project create, file upload (multipart), conversation inside the project, team sharing |
| `tasks.spec.ts` | Run now → navigates to the run's conversation → completes; schedule shows cron + relative next run |
| `connectors.spec.ts` | catalog status chips (needs-auth vs connected) |

Scripted prompts (see `backend/app/orchestration/mock.py`): "write a file" → Write tool (approval in default mode),
"delete" → Bash rm (always approval), "slow" → slow token stream, "fail" → error event.
