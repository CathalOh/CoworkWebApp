# Runbook: incident controls

| Control | How |
|---|---|
| Drain: stop new runs | `POST /v1/admin/capabilities {"key":"new_runs","enabled":false,"reason":"..."}` (in-flight runs finish) |
| Disable all connectors | key `connectors` |
| Disable web tools | key `web_tools` |
| Disable sandbox/Bash execution | key `sandbox_execution` (Bash removed from tool set; PreToolUse also denies) |
| Disable plugins / local stdio MCP | keys `plugins`, `local_mcp` |
| Stop one run | `POST /v1/runs/{id}/interrupt` (any owner; admins via Admin → Runs) |
| Revoke a user | `POST /v1/admin/users/{id}/status {"status":"disabled"}` (sessions fail on next request) |
| Revoke a connector for everyone | `PATCH /v1/admin/connectors/{id} {"enabled":false}` |
| Rotate secrets | see audit-retention-and-keys.md |

Every switch flip is an audit event (`capability.changed`). Check `/readyz` for Postgres/Redis/ILIAD/sandbox health and
`/metrics` for `run_ttft_seconds`, `approval_latency_seconds`, `runs_*_total`, `http_request_seconds`.
