"""Initial schema: all domain tables from the ORM metadata, plus the partitioned, append-only, hash-chained log
tables (created with raw SQL because SQLAlchemy cannot express partitioning/triggers), pgvector, HNSW index.

Revision ID: 0001
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

LOG_TABLES = ("audit_events", "llm_request_logs", "app_logs")

LOG_DDL = """
CREATE TABLE audit_events (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor_id UUID, actor_type VARCHAR(16) NOT NULL DEFAULT 'user', action VARCHAR(128) NOT NULL,
  entity_type VARCHAR(64), entity_id UUID, request_id TEXT, ip VARCHAR(64),
  before JSONB, after JSONB, stream_key VARCHAR(32) NOT NULL DEFAULT 'main',
  prev_hash BYTEA, row_hash BYTEA NOT NULL,
  PRIMARY KEY (id, ts)
) PARTITION BY RANGE (ts);
;;
CREATE INDEX ix_audit_events_actor ON audit_events (actor_id);
;;
CREATE INDEX ix_audit_events_action ON audit_events (action);
;;
CREATE INDEX ix_audit_events_entity ON audit_events (entity_id);
;;
CREATE INDEX ix_audit_events_stream ON audit_events (stream_key, id);
;;

CREATE TABLE llm_request_logs (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  run_id UUID, user_id UUID, model_id TEXT, request JSONB, response JSONB,
  input_tokens INT, output_tokens INT, cache_read_tokens INT, cache_write_tokens INT,
  cost_usd NUMERIC(12,6), latency_ms INT, pii_key_id TEXT,
  PRIMARY KEY (id, ts)
) PARTITION BY RANGE (ts);
;;
CREATE INDEX ix_llm_request_logs_run ON llm_request_logs (run_id);
;;
CREATE INDEX ix_llm_request_logs_user ON llm_request_logs (user_id);
;;

CREATE TABLE app_logs (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  level VARCHAR(16) NOT NULL, logger TEXT NOT NULL, message TEXT NOT NULL, context JSONB, request_id TEXT,
  PRIMARY KEY (id, ts)
) PARTITION BY RANGE (ts);
;;
CREATE INDEX ix_app_logs_request ON app_logs (request_id);
;;

-- append-only enforcement at the DB layer
CREATE OR REPLACE FUNCTION forbid_log_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'table % is append-only', TG_TABLE_NAME;
END; $$ LANGUAGE plpgsql;
;;
CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION forbid_log_mutation();
;;

-- monthly partition management: ensure partitions for the current and next N months exist
CREATE OR REPLACE FUNCTION ensure_log_partitions(months_ahead INT DEFAULT 3) RETURNS void AS $$
DECLARE t TEXT; d DATE; p TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['audit_events','llm_request_logs','app_logs'] LOOP
    FOR i IN -1..months_ahead LOOP
      d := date_trunc('month', now())::date + (i || ' months')::interval;
      p := t || '_' || to_char(d, 'YYYY_MM');
      IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = p) THEN
        EXECUTE format('CREATE TABLE %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)', p, t, d, (d + interval '1 month')::date);
      END IF;
    END LOOP;
  END LOOP;
END; $$ LANGUAGE plpgsql;
;;
SELECT ensure_log_partitions(3);
;;

-- hash-chain head anchoring target (an admin job copies the latest row_hash per stream to external WORM storage)
CREATE TABLE audit_chain_anchors (
  id BIGSERIAL PRIMARY KEY, ts TIMESTAMPTZ NOT NULL DEFAULT now(), stream_key VARCHAR(32) NOT NULL,
  head_id BIGINT NOT NULL, head_hash BYTEA NOT NULL, anchored_to TEXT
);
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("CREATE EXTENSION IF NOT EXISTS citext")
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    tables = [t for t in Base.metadata.sorted_tables if t.name not in LOG_TABLES]
    Base.metadata.create_all(bind=bind, tables=tables)
    if bind.dialect.name == "postgresql":
        for stmt in LOG_DDL.split("\n;;\n"):
            if stmt.strip():
                op.execute(sa.text(stmt))
        op.execute("CREATE INDEX IF NOT EXISTS ix_embeddings_hnsw ON embeddings USING hnsw (embedding vector_cosine_ops)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_messages_text_trgm ON messages USING gin (text_cache gin_trgm_ops)")
        # application role must never be able to mutate logs even if the trigger were dropped
        op.execute(sa.text("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_role') THEN CREATE ROLE app_role; END IF;
        END $$;"""))
        op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM app_role")
    else:
        Base.metadata.create_all(bind=bind, tables=[t for t in Base.metadata.sorted_tables if t.name in LOG_TABLES])


def downgrade() -> None:
    bind = op.get_bind()
    for t in reversed(Base.metadata.sorted_tables):
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{t.name}" CASCADE' if bind.dialect.name == "postgresql" else f'DROP TABLE IF EXISTS "{t.name}"'))
    if bind.dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS audit_chain_anchors")
        op.execute("DROP FUNCTION IF EXISTS forbid_log_mutation CASCADE")
        op.execute("DROP FUNCTION IF EXISTS ensure_log_partitions")
