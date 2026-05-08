# Variant Viewer — Refactor to Option A (FastAPI + React SPA)

- **Date:** 2026-05-04
- **Author:** Joo Wook Ahn
- **Reviewer:** Becky Locke, Matt Garner
- **Confluence:** https://cuhbioinformatics.atlassian.net/wiki/spaces/DV/pages/4681498821

## Summary

The variant-viewer application is being refactored from its original Next.js 15 / TypeScript monolith to a decoupled Python/FastAPI backend and React SPA frontend (Option A from the Python Migration Assessment). This document records the rationale for that decision, the GitHub repository housekeeping that was done to prepare for the refactor, and the planned PR sequence for the rebuild.

The original Next.js codebase is preserved in full as the `discovery/nextjs` branch and tagged at `v0.1-discovery-nextjs`. No code history has been lost.

**Overall status:** Refactor in progress.

## Useful linked documentation

| Resource | Link |
| --- | --- |
| GitHub repository | [eastgenomics/variant-viewer](https://github.com/eastgenomics/variant-viewer) |
| PR 1 — Scaffold (wipe + new structure) | [PR #16](https://github.com/eastgenomics/variant-viewer/pull/16) |
| Python Migration Assessment | [Confluence page](https://cuhbioinformatics.atlassian.net/wiki/spaces/DV/pages/4673994824) / [docs/python-migration-assessment.md](python-migration-assessment.md) |
| `discovery/nextjs` — original Next.js codebase | [branch](https://github.com/eastgenomics/variant-viewer/tree/discovery/nextjs) |
| `discovery/gms-concordance` — GMS concordance prototype | [branch](https://github.com/eastgenomics/variant-viewer/tree/discovery/gms-concordance) |
| `v0.1-discovery-nextjs` — tagged release of original app | [release tag](https://github.com/eastgenomics/variant-viewer/releases/tag/v0.1-discovery-nextjs) |

## Design

### Rationale for Option A

A full Python Migration Assessment was completed in April 2026 (see link above). Three migration architectures were evaluated:

- **Option A** — FastAPI backend + React SPA (Vite): 4–6 weeks estimated effort
- **Option B** — FastAPI + HTMX + Jinja2 templates: 10–16 weeks estimated effort
- **Option C** — Django + HTMX: 10–16 weeks estimated effort

Option A was selected because:

- Risk is concentrated in the right place — the business logic and API routes (where Python expertise is most valuable) are fully migrated. The React UI, which currently works correctly, is preserved almost intact.
- The VCF parser and ingest pipeline are the core of the application's clinical value. Python's bioinformatics ecosystem (`pysam`, `cyvcf2`) may genuinely improve these components.
- The React components contain almost no Next.js-specific code. Migrating the frontend is closer to a scaffolding task than a rewrite.
- A 4–6 week backend rewrite can be scoped as a single sprint. Options B and C involve a 3–4 month effort.
- Option A can evolve into Option B incrementally — individual React components can be replaced with HTMX partials over time without a big-bang rewrite.

### Repository structure

The repo is structured as a monorepo with two main sections:

```
variant-viewer/
├── backend/           Python/FastAPI — API routes, business logic, Lambda handler
│   ├── app/
│   │   ├── main.py
│   │   ├── routes/    9 REST endpoints
│   │   └── lib/       vcf_parser, classification_engine, ingest, db, etc.
│   ├── config/        JSON classification config (acgs-snv-criteria, svig-criteria, etc.)
│   ├── lambda/        ingest_handler.py (S3-triggered async ingest)
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/          React SPA — Vite + React Router + TanStack Table
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   └── lib/
│   ├── package.json
│   └── Dockerfile
├── migrations/        PostgreSQL schema migrations (unchanged)
├── terraform/         AWS infrastructure (unchanged)
└── docker-compose.yml backend + frontend + postgres
```

### Branch structure

| Branch | Role |
| --- | --- |
| `main` | Active development — default branch, protected |
| `discovery/nextjs` | Frozen reference — original Next.js 15 + TypeScript app |
| `discovery/gms-concordance` | Frozen reference — GMS concordance prototype |

A release tag `v0.1-discovery-nextjs` marks the exact commit of the original Next.js codebase before any refactoring began.

### What is unchanged in any option

- PostgreSQL database schema and SQL migrations
- AWS infrastructure (ECS Fargate, ALB, RDS, S3, Secrets Manager, VPC) — Terraform unchanged
- JSON classification framework config files (`acgs-snv-criteria.json`, `svig-criteria.json`, `canvig-gene-mtaf.json`) — moved to `backend/config/`
- FHIR manifest schema (`manifest-schema.json`) and example manifests
- Docker Compose local development configuration (with updated app container image)

## Changes

First release of the refactored codebase. Key changes from `v0.1-discovery-nextjs`:

- All Next.js/TypeScript source removed (`app/`, `components/`, `lib/`, `lambda/`)
- `backend/` scaffold added: FastAPI app, Dockerfile, requirements.txt, `/api/health` stub
- `frontend/` scaffold added: Vite + React Router + TanStack Table package.json, Dockerfile
- `config/` moved to `backend/config/` (contents unchanged)
- `docker-compose.yml` updated for backend + frontend + postgres services
- Branch housekeeping: `main` renamed from Next.js codebase, `discovery/*` branches created

## PRs

| PR | Title | Status |
| --- | --- | --- |
| 1 | [Scaffold — wipe + new structure](https://github.com/eastgenomics/variant-viewer/pull/16) | Merged |
| 2 | Database layer (db.py, Pydantic models) | Done |
| 3 | Business logic: VCF parser + FHIR manifest | Done |
| 4 | Business logic: classification engine + pre-compute criteria | Done |
| 5 | Business logic: ingest + Lambda handler | Done |
| 6 | API routes (read-only): /variants, /patients, /samples, /health | Pending |
| 7 | API routes (write): /classification, /ingest, /upload-url, /workflow | Pending |
| 8 | Frontend scaffold: Vite + React Router, API client, layout shell | Pending |
| 9 | Frontend: VariantTable component | Pending |
| 10 | Frontend: ClassificationPanel component | Pending |
| 11 | Frontend: UploadForm + remaining components | Pending |
| 12 | Infrastructure: Dockerfile, docker-compose, Terraform Lambda runtime | Pending |

## Test setup

Branch: `scaffold` | Commit: [e8640e9](https://github.com/eastgenomics/variant-viewer/commit/e8640e9) | PR: [PR #16](https://github.com/eastgenomics/variant-viewer/pull/16)

No external services required — all config integrity tests run against local files only.

Run tests from `backend/`:

```shell
cd backend
python3 -m venv .venv
.venv/bin/pip install pytest pyyaml
.venv/bin/pytest tests/test_config_integrity.py -v
```

## Testing

### Summary

| Module | Tests | Passed | Outcome |
| --- | --- | --- | --- |
| Config file presence | 5 | 5 | ✅ PASS |
| ACGS SNV criteria | 35 | 35 | ✅ PASS |
| SVIG-UK criteria | 26 | 26 | ✅ PASS |
| CANVIg gene list | 8 | 8 | ✅ PASS |
| Manifest JSON schema | 3 | 3 | ✅ PASS |
| Pipelines YAML | 4 | 4 | ✅ PASS |
| **Total** | 81 | 81 | ✅ 81/81 PASS |

### Test 1: Config file presence

Verified that all five configuration files are present in `backend/config/` after being moved from `config/` during the scaffold refactor.

Files checked: `acgs-snv-criteria.json`, `svig-criteria.json`, `canvig-gene-mtaf.json`, `manifest-schema.json`, `pipelines.yaml`

Method: parametrised pytest test asserting each path exists. Run without any external dependencies.

**Outcome: 5/5 PASS**

### Test 2: ACGS SNV criteria integrity

Verified structural completeness of the ACGS 2024 Best Practice Guidelines SNV classification criteria config.

- All 28 criterion codes present and no extras (PVS1, PVS1_RNA, PS1–PS4, PM1–PM6, PP1–PP4, BA1, BS1–BS4, BP1–BP5, BP7, BP7_RNA)
- Each criterion has required keys: `code`, `label`, `category`, `direction`, `default_strength`, `permitted_strengths`, `adjustable`, `description`, `pre_computable`
- All direction values are valid (`pathogenic` or `benign`)
- Pathogenic threshold = 10, benign threshold = −7, VUS range = 0–5
- Framework identifier = `acgs_snv`

**Outcome: 35/35 PASS**

### Test 3: SVIG-UK criteria integrity

Verified structural completeness of the SVIG-UK v1.0 somatic variant classification criteria config.

- All 18 criterion codes present and no extras (O1–O11, B1–B7)
- Each criterion has the same required key set as ACGS SNV
- All direction values are valid (`oncogenic` or `benign`)
- Oncogenic threshold = 10, benign threshold = −7
- Framework identifier = `svig`

**Outcome: 26/26 PASS**

### Test 4: CANVIg gene list integrity

Verified the CANVIg gene MTAF (Minimum Total Allele Frequency) lookup table retained all 33 genes with non-null entries.

- Gene count = 33
- Key genes present: BRCA1, BRCA2, MLH1, MSH2, MSH6
- No null entries in the gene map

**Outcome: 8/8 PASS**

### Test 5: FHIR manifest JSON schema

Verified the `manifest-schema.json` is a valid JSON Schema with the required structural elements.

- `$schema` or `type` key present
- `properties` key present
- `required` array present and non-empty

**Outcome: 3/3 PASS**

### Test 6: Pipelines YAML

Verified the `pipelines.yaml` is valid YAML with the expected pipeline registry structure.

- Top-level `pipelines` key present
- At least one pipeline defined
- `dragen_germline` pipeline present
- All pipelines have a `label` field

**Outcome: 4/4 PASS**

### Planned tests (future PRs)

- **PR 3** — VCF parser: golden-output tests using existing test VCF files; Python parser must produce identical parsed records to the original TypeScript implementation
- **PR 4** — Classification engine: golden-output tests generated from the TypeScript engine against known variant inputs; Python port must produce identical ACGS SNV and SVIG-UK scores
- **PR 6/7** — API routes: pytest + httpx integration tests against a local PostgreSQL instance via docker-compose
- **PR 9/10** — Frontend components: Vitest + React Testing Library (adapted from existing Jest test suite)

Test file: [backend/tests/test_config_integrity.py](https://github.com/eastgenomics/variant-viewer/blob/scaffold/backend/tests/test_config_integrity.py)
