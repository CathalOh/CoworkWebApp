# ADR-004: DB-stored, append-only, HMAC hash-chained audit log

**Status:** accepted · **Date:** 2026-09-10

## Context
Hosted Cowork activity is excluded from Anthropic's Audit Logs / Compliance API / Data Exports on every tier; the backbone
must provide it.

## Decision
`audit_events` is RANGE-partitioned by month; each row stores `prev_hash` and `row_hash = HMAC(key, prev_hash ||
canonical_json(fields))`, chained per monthly `stream_key` so a chain never crosses a partition. Appends are serialized
per stream with a Postgres advisory lock. Immutability is enforced at the DB: `BEFORE UPDATE OR DELETE` trigger raises,
and `UPDATE/DELETE/TRUNCATE` are revoked from `app_role`. `record_audit` is always called inside the transaction of the
privileged mutation. `GET /v1/admin/audit/verify` recomputes chains; `audit_chain_anchors` holds heads to anchor externally.
PII in `llm_request_logs` is addressed by destroyable keys (`pii_key_id`) rather than row deletion.

## Consequences
Auditors (`auditor` role, read-only) get a viewer, verification and JSONL export. Retention is by partition drop, never
by row delete (see runbook).
