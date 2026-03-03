-- Migration 003: Audit log (clinical governance)

BEGIN;

CREATE TABLE audit_log (
  id           SERIAL PRIMARY KEY,
  user_id      TEXT,
  action       TEXT NOT NULL,        -- e.g. classify, update_workflow, ingest
  entity_type  TEXT NOT NULL,        -- patient | sample | variant | classification | workflow
  entity_id    INTEGER NOT NULL,
  old_value    JSONB,
  new_value    JSONB,
  occurred_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON audit_log(entity_type, entity_id);
CREATE INDEX ON audit_log(occurred_at);

COMMIT;
