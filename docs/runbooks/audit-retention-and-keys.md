# Runbook: log retention, partitions, chain anchoring, key rotation

## Partitions
Monthly partitions for `audit_events`, `llm_request_logs`, `app_logs` are created by `ensure_log_partitions(3)` (migration
0001 calls it once). Schedule it monthly: `SELECT ensure_log_partitions(3);` (e.g. a cron container or a DBA job).

## Retention
* `app_logs` 30 d, `llm_request_logs` 180 d, `run_events` 7 d — `retention_sweep` (arq cron, 03:15 daily) deletes rows.
* `audit_events` ≥ 365 d and **never** row-deleted (trigger + REVOKE). Retire by `DROP TABLE audit_events_YYYY_MM` after
  exporting (`GET /v1/admin/audit/export?since=…`) and anchoring the partition's chain head.

## Chain anchoring
Weekly: `GET /v1/admin/audit/verify` → for each stream copy `head` into `audit_chain_anchors` and to external WORM storage
(object lock bucket / ticketing system). A later verify that changes an anchored head is a tamper signal.

## Erasure (GDPR) without breaking chains
Audit rows keep only identifiers and non-PII metadata. PII in `llm_request_logs` is encrypted with a per-subject key
referenced by `pii_key_id`; destroy the key to render it unreadable while keeping token/cost accounting.

## Key rotation (envelope encryption)
Add the new master key version to the KMS provider (`MasterKeyProvider` keys map), bump `current_version`, then re-wrap
DEKs: `crypto.rewrap(Envelope(...))` per `connector_credentials` row (no token re-encryption). Keep old versions readable
until all rows report the new `key_version`.
