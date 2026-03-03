-- Migration 002: Classification tables

BEGIN;

CREATE TABLE variant_classification (
  id                  SERIAL PRIMARY KEY,
  variant_id          INTEGER NOT NULL REFERENCES variants(id) ON DELETE CASCADE,
  framework           TEXT NOT NULL CHECK (framework IN ('acgs_snv', 'svig')),
  framework_version   TEXT NOT NULL,
  score               INTEGER,
  classification      TEXT,         -- Pathogenic | Likely_Pathogenic | VUS | Likely_Benign | Benign | Oncogenic | Likely_Oncogenic
  locked_at           TIMESTAMPTZ,  -- NULL until analyst confirms
  locked_by           TEXT,
  deleted_at          TIMESTAMPTZ   -- soft-delete for reset
);

CREATE TABLE classification_criterion (
  id                   SERIAL PRIMARY KEY,
  classification_id    INTEGER NOT NULL REFERENCES variant_classification(id) ON DELETE CASCADE,
  criterion_code       TEXT NOT NULL,   -- e.g. PVS1, PP3, O4
  applied              BOOLEAN NOT NULL DEFAULT FALSE,
  strength             TEXT NOT NULL,   -- very_strong | strong | moderate | supporting | standalone
  notes                TEXT,
  evidence_links       TEXT[],          -- flat array; future: normalise to evidence_link table
  pre_computed         BOOLEAN NOT NULL DEFAULT FALSE,
  pre_computed_value   TEXT             -- e.g. "gnomAD AF = 0.0003"
);

-- Indexes
CREATE INDEX ON variant_classification(variant_id);
CREATE INDEX ON classification_criterion(classification_id);

-- Partial index: active (non-deleted) classifications per variant
CREATE INDEX ON variant_classification(variant_id) WHERE deleted_at IS NULL;

COMMIT;
