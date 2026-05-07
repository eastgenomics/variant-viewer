# variant-viewer backend core — PRs 2–5

Database layer, VCF parser, FHIR manifest handler, classification engine,
pre-compute criteria modules, and Lambda ingest pipeline for the Variant Viewer
FastAPI backend.

## What this build delivers

This specification now covers PRs 2–5 of the Option A refactor.

1. **PR 2 — Database layer** — `db.py` (psycopg2 connection pool + AWS Secrets
   Manager resolution) and `models.py` (Pydantic v2 entities for every DB table).
2. **PR 3 — VCF parser + FHIR manifest** — `vcf_parser.py` (hand-rolled VCF
   stream parser, replaced by cyvcf2 in PR 5), `fhir_manifest.py` (FHIR R4
   Bundle parser/builder), and `pipeline_config.py` (YAML pipeline config loader
   and header-based pipeline detection).
3. **PR 4 — Classification engine + pre-compute criteria** — `classification_engine.py`
   (Tavtigian point-based ACGS SNV and SVIG-UK scoring) and
   `pre_compute_criteria.py` (rule-based criterion suggestions from VCF INFO
   annotations). PR 4 requires golden-output test fixtures generated from the
   TypeScript implementation **before** any Python code is written.
4. **PR 5 — Lambda ingest pipeline + cyvcf2 migration** — `ingest.py`
   (S3 download, manifest validation, DB write orchestration) and the Lambda
   handler. Also migrates `vcf_parser.py` from the hand-rolled parser to
   `cyvcf2` (htslib) for BCF, symbolic allele, and future CNV support.

## Status of this document set

These documents are the **complete design and build specification**. A fresh
agent session (or a human developer) should be able to open this directory,
read the files in order, and build a working, tested backend core without
needing the original conversation.

Read in this order:

1. **README.md** (this file) — orientation, project layout, quick start
2. **DESIGN.md** — architecture diagram, module responsibilities, data models,
   error handling, testing strategy, classification algorithm detail
3. **IMPLEMENTATION.md** — ten TDD milestones with full Red/Green/Verify code
4. **REFERENCE.md** — env vars, external deps, complete data format templates,
   config schema, FHIR manifest structure, golden fixture schema

## Project layout (target after PRs 2–5)

```text
variant-viewer/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    FastAPI entry point (pre-existing)
│   │   ├── lambda_handler.py          PR 5 — S3 event handler (Lambda entry point)
│   │   ├── routes/
│   │   │   └── __init__.py
│   │   └── lib/
│   │       ├── __init__.py
│   │       ├── db.py                  PR 2 — connection pool + Secrets Manager
│   │       ├── models.py              PR 2 — Pydantic entities for all DB tables
│   │       ├── vcf_parser.py          PR 3 (hand-rolled) → PR 5 (cyvcf2/htslib)
│   │       ├── fhir_manifest.py       PR 3 — FHIR R4 Bundle parser + builder
│   │       ├── pipeline_config.py     PR 3 — YAML pipeline config + header detection
│   │       ├── classification_engine.py  PR 4 — Tavtigian scoring (pure functions)
│   │       ├── pre_compute_criteria.py   PR 4 — auto-suggest criteria from VCF INFO
│   │       └── ingest.py              PR 5 — S3 download + manifest validation + DB write
│   ├── config/
│   │   ├── acgs-snv-criteria.json     ACGS 2024 criteria + combination rules
│   │   ├── svig-criteria.json         SVIG-UK v1.0 criteria + combination rules
│   │   ├── canvig-gene-mtaf.json      CanVIG gene-specific AF thresholds (33 genes)
│   │   ├── manifest-schema.json       JSON Schema for FHIR Bundle manifest
│   │   └── pipelines.yaml             Pipeline config (labels, filters, patterns)
│   ├── tests/
│   │   ├── test_config_integrity.py   Pre-existing — 81 config integrity tests
│   │   ├── test_models.py             PR 2 — Pydantic model validation
│   │   ├── test_db.py                 PR 2 — pool + transaction (mocked psycopg2)
│   │   ├── test_pipeline_config.py    PR 3 — YAML loader + pipeline detection
│   │   ├── test_fhir_manifest.py      PR 3 — manifest parser
│   │   ├── test_vcf_parser.py         PR 3 (inline strings) → PR 5 (tmp_path + cyvcf2)
│   │   ├── test_ingest.py             PR 5 — ingest orchestration (mocked S3 + DB)
│   │   ├── golden/
│   │   │   ├── classify_acgs_cases.json   PR 4 — ACGS SNV golden I/O
│   │   │   ├── classify_svig_cases.json   PR 4 — SVIG-UK golden I/O
│   │   │   ├── select_framework_cases.json  PR 4 — framework selection golden I/O
│   │   │   └── pre_compute_cases.json     PR 4 — pre-compute criterion golden I/O
│   │   ├── test_classification_engine.py  PR 4 — engine against golden fixtures
│   │   └── test_pre_compute_criteria.py   PR 4 — pre-compute against golden fixtures
│   ├── pytest.ini
│   ├── requirements.in            Direct dependencies (pip-compile source)
│   ├── requirements.txt           Hash-pinned transitive deps (pip-compile output)
│   └── Dockerfile
├── migrations/                        Unchanged — PostgreSQL schema
├── terraform/                         Unchanged — AWS infrastructure
└── specification/                     This document set
```

## Quick start (once built)

```bash
# 1. Enter backend directory and activate virtual environment
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Run all tests (includes pre-existing 81 config integrity tests)
.venv/bin/pytest -v

# 3. Verify classification engine golden tests specifically
.venv/bin/pytest tests/test_classification_engine.py -v

# 4. Check coverage
.venv/bin/pytest --cov=app --cov-report=term-missing
```

## Target user

A clinical bioinformatics developer building the Variant Viewer FastAPI backend
(the Option A refactor). They have read the TypeScript source on the
`discovery/nextjs` branch and need the Python equivalents to be
behaviourally identical — same scores, same classifications, same edge-case
handling — verified by golden-output tests derived from the TypeScript engine.

## Non-goals

- **No FastAPI routes in this spec** — API endpoints are PR 6/7.
- **No Lambda ingest orchestration in PRs 2–4** — the S3 + DB ingest pipeline
  is PR 5, specified in IMPLEMENTATION.md Milestones 11–13.
- **No frontend components** — React SPA is PRs 8–11.
- **No Terraform / infrastructure changes** — the existing ECS/RDS/ALB stack is
  unchanged in all three PRs.
- **No external annotation lookups** — `pre_compute_criteria.py` works only from
  fields already present in the VCF INFO column; it does not call ClinVar,
  gnomAD, or SpliceAI APIs.
- **No async DB driver** — `db.py` uses psycopg2 (synchronous) to match the
  existing `requirements.txt`; migration to asyncpg is deferred.
- **No full FHIR validation library** — `fhir_manifest.py` is a typed lightweight
  parser, not a HAPI-FHIR equivalent; JSON Schema validation of the bundle
  structure is done by the ingest layer in PR 5.
