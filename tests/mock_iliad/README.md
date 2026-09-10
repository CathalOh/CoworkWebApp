# mock-iliad — local stand-ins for ILIAD, a remote MCP server, its OAuth AS, and PingID

One FastAPI process on **port 9100** that replaces every external dependency of the Cowork backbone during local
development and e2e tests. Nothing here talks to the network; all state is in memory and resets on restart.

| Prefix | What it mocks | Module |
|---|---|---|
| `/v1/*` | **ILIAD** exposing the Anthropic Messages API (`ANTHROPIC_BASE_URL`) | `anthropic_api.py` |
| `/mcp` | a remote **MCP server** ("mock-drive", streamable HTTP) protected by OAuth | `mcp_server.py` |
| `/.well-known/*`, `/oauth/*` | the **OAuth 2.1 authorization server** for `/mcp` (PKCE, DCR, refresh rotation, RFC 8707 `resource`) | `oauth_as.py` |
| `/oidc/*` | an **OIDC provider** (PingID / PingOne stand-in), issuer `http://localhost:9100/oidc` | `oidc.py` |

`server.py` wires the routers together, logs every request line to stdout, and adds `GET /` (endpoint index) and
`GET /healthz`. `common.py` holds shared helpers (PKCE S256, opaque tokens, tiny HTML pages).

## Running

```bash
cd tests/mock_iliad
pip install -r requirements.txt
uvicorn server:app --port 9100            # http://localhost:9100/docs has the OpenAPI UI
pytest -q                                 # in-process tests (httpx ASGITransport), ~1s
docker build -t mock-iliad . && docker run -p 9100:9100 mock-iliad
```

`docker-compose.yml` at the repo root builds this directory as the `mock-iliad` service; `scripts/dev.sh` starts it.

The only configuration knob is `MOCK_BASE_URL` (default `http://localhost:9100`): the origin written into the
discovery documents (`resource`, `authorization_servers`, OIDC `issuer`, endpoint URLs).

## Pointing the backend at it

```bash
MODEL_PROVIDER=iliad_anthropic          # -> IliadAnthropicProvider (AgentSdkRuntime); "mock" also honours ILIAD_BASE_URL
ILIAD_BASE_URL=http://mock-iliad:9100   # becomes ANTHROPIC_BASE_URL for the agent; http://localhost:9100 outside compose
ILIAD_AUTH_TOKEN=mock                   # becomes ANTHROPIC_AUTH_TOKEN; any non-empty value is accepted
OIDC_ISSUER=http://mock-iliad:9100/oidc # discovery at $OIDC_ISSUER/.well-known/openid-configuration
OIDC_CLIENT_ID=cowork-backbone
# OIDC_CLIENT_SECRET may stay unset; the mock accepts public clients and ignores any secret.
```

Note the split-horizon issue inside compose: the **backend** reaches this service as `mock-iliad:9100` while the
**browser** reaches it as `localhost:9100`. Because the OIDC issuer in the `id_token` must equal `OIDC_ISSUER`, run the
container with `MOCK_BASE_URL=http://mock-iliad:9100` when the backend runs in compose (the browser is only sent to
the login page, which doesn't care about the host); the `authorization_endpoint` in the discovery document is then
also `mock-iliad`, so add `127.0.0.1 mock-iliad` to `/etc/hosts` — or run the backend on the host with
`OIDC_ISSUER=http://localhost:9100/oidc`, which is what `scripts/dev.sh` does.

The seeded `mock-drive` connector (`backend/app/seed.py`) already points here: `url=http://mock-iliad:9100/mcp`,
explicit `authorization_endpoint=http://localhost:9100/oauth/authorize` (browser-facing) and
`token_endpoint=http://mock-iliad:9100/oauth/token` (backend-facing), `client_id=cowork-backbone`,
`resource=http://mock-iliad:9100/mcp`, scope `drive.read`. `cowork-backbone` is pre-registered in the AS with no
redirect_uri restriction, so the backend's `PUBLIC_BASE_URL/v1/connectors/oauth/callback` works for any
`PUBLIC_BASE_URL`. Connectors without a `client_id` go through dynamic registration instead.

## 1. Mock ILIAD — Anthropic Messages API

* `GET /v1/models` → `{"data":[{"id":"claude-opus-5"},{"id":"claude-sonnet-5"}], ...}`.
  **Unauthenticated on purpose**: the compose healthcheck and `IliadAnthropicProvider.healthcheck()` probe it.
* `POST /v1/messages` → requires `Authorization: Bearer <anything>` **or** `x-api-key: <anything>`, else
  `401 {"type":"error","error":{"type":"authentication_error",...}}`. Any `anthropic-beta` / `anthropic-version`
  header is accepted. Body fields understood: `model`, `max_tokens`, `system`, `messages`, `tools`, `stream`,
  `thinking`, `metadata`, `tool_choice`; unknown fields are ignored.
  * non-streaming → a full `Message` (`id`, `type:"message"`, `role`, `model`, `content[]`, `stop_reason`,
    `stop_sequence:null`, `usage{input_tokens, output_tokens, cache_read_input_tokens:0, cache_creation_input_tokens:0}`).
  * `stream:true` → `text/event-stream` with the real event order:
    `message_start` → `ping` → per block (`content_block_start`, `content_block_delta`×N, `content_block_stop`) →
    `message_delta` (stop_reason + usage.output_tokens) → `message_stop`. Deltas are `text_delta`,
    `input_json_delta` (tool input split into 3 chunks), `thinking_delta` + `signature_delta`.
  * tokens: `input_tokens ≈ len(json(system+messages+tools))/4`, `output_tokens` = words emitted.

Behaviour is deterministic and decided by the **last user message text** (case-insensitive), in this order:

| Condition | Response |
|---|---|
| last message is a user message with `tool_result` blocks | text `The result is <tool_result content>` — or `Wrote the file.` if the matching `tool_use` was `Write` |
| contains `error500` | HTTP 500 `{"type":"error","error":{"type":"api_error","message":"mock outage"}}` |
| contains `ratelimit` | HTTP 429 `rate_limit_error`, header `retry-after: 1` |
| contains `think` | a `thinking` block `Let me think...` is emitted **before** whichever block below applies |
| contains `use the calculator` or `add ` **and** a tool whose name ends with `add` (e.g. `mcp__calc__add`) | `tool_use` for that tool with `{"a":2,"b":3}`, `stop_reason:"tool_use"` |
| contains `write a file` **and** a tool named `Write` | `tool_use Write {"file_path":"<cwd>/notes.md","content":"hello from mock"}` where `<cwd>` is parsed from a `Working directory: /path` line in the system prompt, else `/ws` |
| otherwise | text `Mock ILIAD reply: <last user text>` |

Every call prints `[mock-iliad] messages model=… stream=… scenario=…` plus the request line.

## 2. Mock remote MCP server (`mock-drive`)

* `POST /mcp` — JSON-RPC 2.0 over streamable HTTP; responses are `application/json` (no SSE upgrade).
  Without a valid bearer token: `401` with
  `WWW-Authenticate: Bearer resource_metadata="http://localhost:9100/.well-known/oauth-protected-resource/mcp"`.
  Only tokens minted by `/oauth/token` on this server are valid.
* `GET /mcp` → 405, `DELETE /mcp` → 204 (session end; sessions are stateless anyway).
* Methods: `initialize` (`protocolVersion "2025-06-18"`, `capabilities {tools:{}}`, `serverInfo {name:"mock-drive"}`,
  plus an `Mcp-Session-Id` header), `notifications/initialized` and any other notification → `202` empty body, `ping`,
  `tools/list` → `list_files {}` and `read_file {path:string}`, `tools/call`:
  `list_files` → text `metrics.xlsx\nnarrative.docx` (+ `structuredContent.files`), `read_file` → `contents of <path>`,
  unknown tool → JSON-RPC error `-32602`; unknown method → `-32601`; batches → `-32600`.

## 3. OAuth 2.1 authorization server (for `/mcp`)

| Endpoint | Notes |
|---|---|
| `GET /.well-known/oauth-protected-resource/mcp` and `/.well-known/oauth-protected-resource` | RFC 9728: `{"resource":"http://localhost:9100/mcp","authorization_servers":["http://localhost:9100"], ...}` |
| `GET /.well-known/oauth-authorization-server` | RFC 8414: `issuer`, `authorization_endpoint`, `token_endpoint`, `registration_endpoint`, `code_challenge_methods_supported:["S256"]`, `grant_types_supported`, `response_types_supported`, … |
| `POST /oauth/register` | RFC 7591 DCR for public clients → `201 {client_id, redirect_uris, …}`; the client is pinned to its `redirect_uris` |
| `GET /oauth/authorize` | validates `client_id`, `redirect_uri`, `response_type=code`, `code_challenge` (+ `code_challenge_method=S256`), optional `scope`, `state`, `resource`; renders a consent page with an **Approve** form and a **Deny** link. Unknown client / bad redirect → 400 JSON; other errors → redirect with `error=…` |
| `GET /oauth/authorize?...&auto_approve=1` | **test shortcut**: skips the consent page and redirects straight to `redirect_uri?code=…&state=…` |
| `GET\|POST /oauth/authorize/decision` | `req_id` + `decision=approve` → redirect with `code`+`state`; anything else → `error=access_denied&state=…` |
| `POST /oauth/token` (form-encoded) | `grant_type=authorization_code`: checks code (single use, 5 min), `client_id`, `redirect_uri`, S256 `code_verifier`, and `resource` if both sides supplied one → `{access_token, token_type:"Bearer", expires_in:3600, refresh_token, scope}`. `grant_type=refresh_token`: rotates (old refresh **and** access token are revoked). Errors are RFC 6749 `{error, error_description}` with 400 (401 for unknown client). |

Tokens are opaque `secrets.token_urlsafe` strings. Pre-registered client: `cowork-backbone` (any redirect_uri).

## 4. Mock OIDC provider (PingID stand-in), issuer `http://localhost:9100/oidc`

| Endpoint | Notes |
|---|---|
| `GET /oidc/.well-known/openid-configuration` | `issuer`, `authorization_endpoint`, `token_endpoint`, `jwks_uri`, `userinfo_endpoint`, `end_session_endpoint`, `introspection_endpoint`, `code_challenge_methods_supported:["S256"]`, … |
| `GET /oidc/jwks` | one RSA-2048 key generated at startup, `kid "mock-1"`, RS256 |
| `GET /oidc/authorize` | login form: **email** + **groups** (comma separated, default `cw-org-admins` → `org_admin` via `ROLE_GROUP_MAP_JSON`). Honours `state`, `nonce`, `code_challenge` (S256). Any `client_id` is accepted. |
| `GET /oidc/authorize?...&auto=1&email=lead@example.com&groups=cw-team-leads,cw-developers` | **test shortcut**: submits the form for you and redirects with `code`+`state` (email defaults to `admin@example.com`) |
| `POST /oidc/authorize/login` | form target (`req_id`, `email`, `groups`) |
| `POST /oidc/token` | `authorization_code` (+PKCE when a challenge was sent; `client_id` from the form or HTTP basic auth, secret ignored) and `refresh_token` (rotating) → `{id_token, access_token, refresh_token, token_type, expires_in:3600, scope}`. `id_token` claims: `iss`, `sub="mock|<email>"`, `aud=<client_id>`, `email`, `email_verified`, `name`, `groups[]`, `nonce`, `iat`, `exp`, `auth_time` |
| `POST /oidc/introspect` | RFC 7662 `{active:true, sub, email, groups, client_id, scope, exp, iat}` or `{active:false}` |
| `GET /oidc/userinfo` | bearer access_token → claims |
| `GET /oidc/logout` | end_session: 302 to `post_logout_redirect_uri` (with `state`), else a plain-text page |

## Tests

`test_mock_server.py` runs against the ASGI app in-process (no port needed) and covers: model list + auth,
non-streaming and streaming messages (full SSE parse), calculator tool-use round trip, Write + thinking, 500/429
scenarios, MCP 401 → RFC 9728/8414 discovery → DCR → `auto_approve` → token → refresh rotation → `initialize` /
`tools/list` / `tools/call`, the consent page approve/deny paths and PKCE failures, and OIDC discovery → PKCE login →
`id_token` verification against the JWKS with python-jose → introspection → refresh → logout.
