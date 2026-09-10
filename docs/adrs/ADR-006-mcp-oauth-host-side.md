# ADR-006: Remote-MCP OAuth 2.1 + PKCE is run by the backbone, per user

**Status:** accepted · **Date:** 2026-09-10

## Context
The Agent SDK does not run an interactive OAuth flow; credentials must be supplied via the MCP server's `headers`.

## Decision
`app/mcp_host/oauth.py` implements discovery (RFC 9728 → RFC 8414), DCR (RFC 7591), Authorization Code + PKCE (S256),
`resource` binding (RFC 8707) and refresh. `POST /v1/connectors/{id}/authorize` returns the authorization URL; the
callback exchanges the code server-side; tokens are envelope-encrypted (per-record DEK wrapped by a versioned master
key; access + refresh under one DEK). At run start `build_mcp_servers` injects `Authorization: Bearer` and reports
`connected | needs-auth | disabled`. Tool allow-listing uses `mcp__<server>__<tool>` patterns from the catalog; connector
actions that look irreversible (send/pay/publish/delete…) always require approval; `bypassPermissions` is never used.

## Consequences
Only org-approved catalog entries (optionally team-scoped) are reachable. Elicitation has a host-side UI + control channel
even though the Python SDK does not yet expose the hook.
