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

-- Enforce append-only: prevent UPDATE/DELETE on audit_log
CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_no_update
BEFORE UPDATE ON audit_log
FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();

CREATE TRIGGER audit_log_no_delete
BEFORE DELETE ON audit_log
FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();

COMMIT;
