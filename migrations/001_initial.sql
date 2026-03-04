-- Migration 001: Core tables
-- patients, samples, variants, workflow

BEGIN;

CREATE TABLE patients (
  id          SERIAL PRIMARY KEY,
  name        TEXT,
  dob         DATE,
  lab_number  TEXT UNIQUE NOT NULL,
  nhs_number  TEXT UNIQUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE samples (
  id            SERIAL PRIMARY KEY,
  patient_id    INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  vcf_filename  TEXT,
  s3_key        TEXT UNIQUE NOT NULL,
  pipeline_key  TEXT,
  case_type     TEXT NOT NULL CHECK (case_type IN ('germline', 'somatic')),
  tissue        TEXT,
  sequencing_date DATE,
  ingested_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE variants (
  id            SERIAL PRIMARY KEY,
  sample_id     INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
  chrom         TEXT NOT NULL,
  pos           INTEGER NOT NULL,
  ref           TEXT NOT NULL,
  alt           TEXT NOT NULL,
  qual          FLOAT8,             -- NULL for VCF '.' (missing)
  filter        TEXT,
  gene          TEXT,
  consequence   TEXT,
  hgvs_c        TEXT,
  hgvs_p        TEXT,
  gnomad_af     FLOAT8,
  clinvar_sig   TEXT,
  revel_score   FLOAT8,
  spliceai_max  FLOAT8,             -- max delta score across DS_AG, DS_AL, DS_DG, DS_DL
  info_json     JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE workflow (
  id          SERIAL PRIMARY KEY,
  sample_id   INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
  status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'reviewing', 'reported', 'archived')),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_by  TEXT
);

-- Indexes
CREATE INDEX ON samples(patient_id);
CREATE INDEX ON variants(sample_id);
CREATE INDEX ON variants(gene);
CREATE INDEX ON variants(chrom, pos);
CREATE INDEX ON workflow(sample_id);

COMMIT;
