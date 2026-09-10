# Cowork frontend

React 18 + TypeScript SPA (Vite, react-router v6, zustand) for the Cowork backbone. It talks to the FastAPI
backend under `/v1` using the HttpOnly session cookie plus an `X-CSRF-Token` header on mutating requests.

## Develop

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /v1, /healthz, /readyz (and the run WebSocket) to :8000
```

Start the backend on `http://localhost:8000` first (set `BACKEND_ORIGIN` to point the dev proxy elsewhere).
With `DEV_LOGIN` enabled on the backend, the login page offers an email + roles form; with OIDC configured it
offers a single-sign-on button that navigates to `/v1/auth/login`.

Environment: `VITE_API_BASE` (default empty = same origin). Set it only when the API is on another origin;
the backend's CORS `frontend_origin` must then match.

## Check & build

```bash
npm run typecheck    # tsc --noEmit
npm run build        # typecheck + vite build → dist/
```

## Docker

```bash
docker build -t cowork-frontend .
docker run -p 8080:80 --network <compose-network> cowork-frontend
```

`nginx.conf` serves `dist/` with SPA fallback and proxies `/v1`, `/healthz`, `/readyz`, `/docs` to
`http://backend:8000` with WebSocket upgrade and `proxy_buffering off` so SSE streams flow.

## Layout

```
src/
  lib/api        fetch client (cookies, CSRF, problem+json), typed endpoints, wire types
  lib/sse        resumable EventSource wrapper for /v1/runs/{id}/events
  lib/oidc       login/logout navigation helpers
  lib/markdown   dependency-free, HTML-safe markdown → React renderer
  store          zustand stores: auth, chat (live run state + resume), toast, ui
  components     AppShell, Toast, Modal, ConfirmDialog, SearchPalette (Cmd/Ctrl+K), chips…
  slots          UI slot registry (+ README) and the demo KpiPanel
  features/      chat, projects, workspaces, artifacts, connectors, tasks, skills (+plugins, memory), admin, auth
```

## Chat streaming notes

- `POST /v1/conversations/{id}/messages` returns a Run; the client opens `GET /v1/runs/{id}/events` with
  `EventSource` (credentials included). Frames carry `id=<seq>` so browser reconnects resume via
  `Last-Event-ID`; the last seen seq is also kept in `localStorage` per run, and the active run id per
  conversation, so a page reload re-attaches to an in-flight run (`GET /v1/runs/{id}` → still active →
  reopen with `?after=`).
- Terminal events (`result`, `error`, `interrupted`) and `status{kind:'closed'}` close the stream; messages
  and runs are then refetched.
- Approvals post to `/v1/runs/{id}/approvals`; elicitations to `/v1/runs/{id}/elicitations`; Stop posts to
  `/v1/runs/{id}/interrupt`.

## Artifacts

Rendered in `<iframe sandbox="allow-scripts">` pointing at `/v1/artifacts/{id}/render?version=n`.
Never add `allow-same-origin` — the preview must not be able to reach the session cookie or API.
