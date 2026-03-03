# Genomics Variant Viewer

A web application for reviewing and classifying genomic variants from VCF files, built for diagnostic genomics workflows in a clinical laboratory setting.

Variants are ingested from VCF files, displayed in a filterable table, and classified using UK-standard frameworks (ACGS 2024 SNV/indel and SVIG-UK somatic). Workflow status is tracked per sample.

---

## Contents

- [What this is](#what-this-is)
- [What this is not](#what-this-is-not)
- [Architecture overview](#architecture-overview)
- [Design decisions](#design-decisions)
  - [Framework: Next.js App Router](#framework-nextjs-app-router)
  - [Database: PostgreSQL with raw SQL](#database-postgresql-with-raw-sql)
  - [VCF ingest: S3 + Lambda, shared with API route](#vcf-ingest-s3--lambda-shared-with-api-route)
  - [FHIR R4 Bundle manifest](#fhir-r4-bundle-manifest)
  - [Variant table: TanStack Table with server-side pagination](#variant-table-tanstack-table-with-server-side-pagination)
  - [Classification: point-based scoring engine](#classification-point-based-scoring-engine)
  - [Pre-computation: suggestions from VCF annotations](#pre-computation-suggestions-from-vcf-annotations)
  - [Pipeline-aware filter presets](#pipeline-aware-filter-presets)
  - [AWS infrastructure choices](#aws-infrastructure-choices)
  - [Secrets management](#secrets-management)
  - [Audit log](#audit-log)
- [Schema](#schema)
- [Classification frameworks](#classification-frameworks)
- [Project structure](#project-structure)
- [Known limitations and future work](#known-limitations-and-future-work)

---

## What this is

This module handles one part of a larger diagnostic system: **variant review and classification**. It ingests annotated VCF files (VEP or SnpEff), presents variants to an analyst in a filterable table pre-loaded with sensible pipeline-specific defaults, and guides them through structured classification using ACGS 2024 (germline) or SVIG-UK (somatic) criteria.

The primary design constraint was **maintainability over cleverness**. The codebase is meant to be readable and modifiable by a small team, not impressively abstract.

---

## What this is not

- **Not an all-in-one diagnostic platform.** Authentication, user management, report generation, and IGV visualisation are handled by the surrounding system and are intentionally out of scope here.
- **Not a real-time annotation tool.** All annotation enrichment (gnomAD AF, REVEL, SpliceAI, ClinVar) is expected to have been run by the upstream bioinformatics pipeline and encoded in the VCF INFO field. This app reads those annotations — it does not call external APIs to fetch them.
- **Not suitable for whole-genome VCFs.** The Lambda-based ingest is designed for targeted panels and exomes (typically <500k variants). WGS support would require a different compute approach (ECS batch task).
- **Not a CNV classifier.** CNV classification uses a different ACGS framework with a different evidence model and is a separate problem.

---

## Architecture overview

```
Browser
  │
  ├─ GET/POST pages and API routes
  │       │
  │    Next.js on ECS Fargate
  │       │
  │    PostgreSQL (RDS)
  │
  └─ PUT VCF + manifest
          │
        S3 bucket
          │
        S3 event → Lambda
                    │
                 PostgreSQL (RDS)
```

The web application and the ingest function share the same core library (`lib/ingest.ts`, `lib/vcf-parser.ts`). The Lambda is not a separate codebase — it is a thin entry point that calls the same logic the API route uses for manual re-ingestion.

---

## Design decisions

### Framework: Next.js App Router

**Why Next.js?**
The application needs a server (for database queries, presigned URL generation, and classification persistence) and a client (for the interactive variant table and classification panel). Next.js handles both in one project without a separate API service. This reduces operational complexity and keeps the codebase coherent.

**Why App Router specifically?**
Server Components let the patient list and variant detail pages fetch data directly without an intermediate API call or client-side loading state. The pages that need interactivity (the variant table with live filters, the classification panel with live scoring) are explicitly marked `"use client"`. The boundary between server and client is explicit and intentional rather than implicit.

**Why not a separate frontend + backend?**
For a module of this scope — one team, one deployment, shared context — splitting into two services adds overhead (CORS, separate deployments, separate type systems) without meaningful benefit.

---

### Database: PostgreSQL with raw SQL

**Why PostgreSQL?**
Variant data is relational. Samples belong to patients; variants belong to samples; classification criteria belong to classifications. PostgreSQL's row-level locking, advisory locks, and JSONB support are all used directly. It handles concurrent writes from multiple analysts without any application-level coordination.

**Why raw SQL instead of an ORM?**

ORMs abstract away the database at the cost of transparency. When queries are slow or wrong, you need to understand SQL anyway. For a schema this size, writing SQL directly is not burdensome — there are perhaps a dozen distinct queries in the whole application. The queries are readable, debuggable with `EXPLAIN ANALYZE`, and have no hidden N+1 risk because they are explicit.

`node-postgres` (`pg`) is used directly with a connection pool. `withTransaction` and `withClient` helpers in `lib/db.ts` handle the boilerplate cleanly.

**Why plain SQL migration files?**

Migration tools like Flyway or Liquibase are excellent, but they add a runtime dependency and configuration surface. The migration runner in `scripts/migrate.js` is 40 lines of plain Node.js: read a directory of `.sql` files in order, track which have been applied in a `schema_migrations` table, run the rest. It is easy to understand and easy to extend. There is no magic.

**The `info_json` JSONB column**

VCF INFO fields contain dozens of annotation keys that vary by pipeline and annotator version. Rather than add a column per annotation (a maintenance burden) or ignore non-standard fields (information loss), the raw INFO field is stored as JSONB. Commonly queried fields (gnomAD AF, REVEL, SpliceAI, ClinVar) are promoted to typed columns for indexed filtering. Everything else lives in `info_json` and is accessible without a schema change.

**The `qual` FLOAT8 NULL convention**

The VCF spec uses `.` (a literal dot) to represent a missing QUAL score. Storing `.` as a string would require type casting at every query boundary. Storing `0` would be semantically wrong — a QUAL of 0 is meaningful. The parser maps `.` to `NULL`, which is the correct SQL representation of "unknown". Queries that filter on QUAL use `IS NOT NULL` where appropriate.

---

### VCF ingest: S3 + Lambda, shared with API route

**Why S3 as the intake point?**

VCF files are large. Routing them through the web application adds latency, memory pressure, and a failure mode (app restart mid-upload loses the file). S3 presigned URLs let the browser upload directly without touching the application server. This also means bioinformatics pipelines can deposit files directly into S3 without any web interaction — the same Lambda triggers in both cases.

**Why Lambda for ingest?**

Ingest is event-driven and bursty: nothing happens for hours, then several VCFs arrive at once. A long-running process polling S3 wastes money. Lambda scales to zero, costs nothing when idle, and handles multiple concurrent ingests without contention (advisory locks in PostgreSQL prevent duplicate ingest of the same file).

**Why share code between Lambda and the API route?**

The ingest logic lives in `lib/ingest.ts` and `lib/vcf-parser.ts`. Both the Lambda handler (`lambda/ingest-handler.ts`) and the manual re-ingest API route (`app/api/ingest/route.ts`) call `ingestVcf()` from `lib/ingest.ts`. This means the manual re-ingest path — which exists as a fallback if Lambda failed or a pipeline dropped a file without going through the upload form — is not a second implementation. There is one parser, one batch insert loop, one pre-computation pass.

**Idempotency via advisory lock**

S3 event notifications are at-least-once: the same event can fire twice. The ingest transaction acquires a PostgreSQL advisory lock keyed on `hashtext(s3_key)` before doing anything else. This lock is scoped to the transaction and released on commit or rollback. A second concurrent ingest attempt for the same key will block on the lock, then find that the sample has already been deleted and re-inserted, and commit cleanly with no duplicate data. The delete-then-reinsert pattern means re-running ingest for a corrected VCF is safe.

**Why streaming + batch inserts?**

A 200k-variant exome VCF is ~100 MB uncompressed. Loading the entire file into memory before inserting would require a Lambda with gigabytes of memory. The parser streams line-by-line, and variants are inserted in batches of 1,000 rows per `INSERT`. This keeps memory flat and reduces round-trips to RDS.

---

### FHIR R4 Bundle manifest

**Why a sidecar manifest file?**

VCF files do not carry reliable patient metadata. Sample names in VCF headers are inconsistently formatted and pipeline-specific. Rather than attempt to parse patient identity from the filename or VCF header, every VCF is accompanied by a `.manifest.json` sidecar file at the same S3 prefix. The Lambda reads the manifest first, then the VCF.

**Why FHIR R4?**

FHIR is the standard interchange format for clinical data in the NHS and most UK diagnostic labs. Using a FHIR R4 Bundle (Patient + Specimen + Task) means the manifest format aligns with the broader NHS data model and is compatible with future integration with LIMS, EHR, and Genomics England systems. It also gives the manifest a defined, versioned structure rather than a bespoke JSON schema.

The implementation is a lightweight typed parser in `lib/fhir-manifest.ts` — no full FHIR library is needed, because the manifest structure is fixed and well-known.

**NHS number validation**

NHS numbers use a Luhn modulo-11 checksum. The parser validates the checksum before ingest begins and rejects manifests with an invalid NHS number. This prevents a transposition error in the upload form from silently associating variants with the wrong patient identity. The lab number is always present; the NHS number is optional.

---

### Variant table: TanStack Table with server-side pagination

**Why server-side pagination?**

A single exome sample can have 50,000–500,000 variants before filtering. Sending all of them to the browser at once is not viable. TanStack Table is configured in manual (server-side) mode: sorting, filtering, and page changes all trigger a new `GET /api/variants` request. The server applies `WHERE`, `ORDER BY`, `LIMIT`, and `OFFSET` in SQL — where they belong.

**Why TanStack Table (React Table)?**

TanStack Table is headless: it manages state (sorting, pagination, selection) but renders nothing. The table HTML, the filter controls, and the cell renderers are all custom. This means the table can be styled with Tailwind and extended (e.g. row grouping, column visibility toggles) without fighting an opinionated component library. It has no peer dependencies and no CSS to override.

**Why not a data grid component?**

Off-the-shelf data grids (AG Grid, MUI DataGrid) are large and opinionated. They work well when their defaults align with requirements; they become a source of friction when they don't. For a clinical table where cell rendering (classification badges, colour-coded AF values, HGVS formatting) and filtering behaviour (pipeline presets, consequence allow-lists) are all custom, a headless library is the right choice.

**Filter initialisation from pipeline presets**

When the variant table loads, filters are pre-populated from `config/pipelines.yaml` based on the sample's `pipeline_key`. A DRAGEN germline sample gets `gnomAD AF ≤ 0.01` and a consequence allow-list pre-applied. These are sensible defaults, not hard locks — the analyst can relax or tighten them. The preset is stored on the `samples` table so it is always recoverable if the analyst navigates away and returns.

---

### Classification: point-based scoring engine

**Why implement the scoring engine rather than using a library?**

There is no widely-used open-source library that implements ACGS 2024 + SVIG-UK criteria with the combination rules, CanVIG MTAF overrides, and the exact threshold tables used in UK diagnostic practice. The scoring logic is straightforward: sum points by strength, apply thresholds, check combination rules. It is implemented as a pure function in `lib/classification-engine.ts` — no side effects, no database calls, fully testable.

**Why pure functions?**

The scoring function is called twice: client-side on every criterion toggle (for instant feedback) and server-side on save (for the authoritative stored result). Pure functions make this safe. The client never trusts its own score as final — the server re-derives it from the saved criteria.

**Framework auto-selection**

The framework (ACGS SNV or SVIG-UK) is determined per-variant, not per-sample, based on case type (germline/somatic) and gene. A germline sample in a cancer predisposition gene gets ACGS SNV with CanVIG MTAF overrides; a somatic sample gets SVIG-UK. This logic is in `lib/classification-engine.ts:selectFramework()`. The framework selector in the UI is pre-populated from this function but editable before the first criterion is saved.

**Framework lock on first criterion save**

Once an analyst applies their first criterion, the framework selector is locked. This prevents accidentally switching the framework mid-session, which would invalidate the applied criteria (ACGS codes are not valid SVIG codes and vice versa). If the wrong framework was selected, a "Reset classification" button soft-deletes the current record (`deleted_at`) and starts fresh. The old record is retained for audit purposes — it is never hard-deleted.

**CanVIG gene-specific MTAF thresholds**

ACGS and CanVIG use different allele frequency thresholds for the BA1 (standalone benign) and BS1 criteria, depending on the gene and its associated disease. For example, BRCA1 uses a BA1 threshold of 0.001 rather than the ACGS standard 0.05, because the prevalence of HBOC in the population means a common variant is more likely to be polymorphic rather than causative. These thresholds are stored in `config/canvig-gene-mtaf.json` and loaded at pre-computation time. The gene is taken from the VEP `SYMBOL` annotation on the variant.

---

### Pre-computation: suggestions from VCF annotations

At ingest time, the system scans each variant's annotations and records candidate criteria as suggestions. A REVEL score of 0.82 becomes a PP3 suggestion; a gnomAD AF of 0.00003 becomes a PM2 suggestion; a frameshift consequence in a known gene becomes a PVS1 suggestion.

These suggestions are stored in `classification_criterion` with `applied = FALSE` and `pre_computed = TRUE`. The analyst sees them as pre-populated (but unchecked) rows in the classification panel, with the evidence value displayed as a badge. They must explicitly check each one to apply it — suggestions are never automatically counted in the score.

**Why not auto-apply pre-computed criteria?**

Auto-applying criteria would mean the classification is partially determined without analyst review, which is inappropriate in a clinical setting. The ACGS guidelines require that each criterion is assessed in the context of the specific variant and patient. Pre-computation saves the analyst time by surfacing the relevant evidence; it does not replace their judgement.

**Why at ingest time rather than on demand?**

Pre-computation at ingest means the classification panel loads instantly with suggestions already populated. For a sample with 50,000 variants, computing suggestions on demand for every variant as the analyst opens them would be slower and would require repeated parsing of the stored `info_json`. Running it once at ingest amortises the cost.

---

### Pipeline-aware filter presets

Different sequencing pipelines produce VCFs with different expected variant distributions. A somatic panel pipeline calibrated for tumour VAF detection produces a very different variant spectrum to a germline rare-disease panel. Applying the same allele frequency filter to both would either flood the analyst with noise or hide real variants.

Pipeline presets in `config/pipelines.yaml` encode the appropriate defaults per pipeline: gnomAD AF ceiling, consequence allow-list, and ClinVar exclusion terms. The pipeline is detected from the VCF `##source` header line at ingest; it can be overridden via the upload form dropdown. The detected key is stored in `samples.pipeline_key` and used to initialise the variant table filters on every page load.

This is a config file rather than a database table because pipeline definitions change infrequently and benefit from being version-controlled alongside the code.

---

### AWS infrastructure choices

**ECS Fargate over Lambda for the web app**

Lambda cold starts are acceptable for the ingest function (which runs asynchronously in the background) but not for a web application where analysts are waiting for responses. ECS Fargate runs the Next.js server as a persistent container. It is also simpler to reason about: the container behaves identically locally and in production.

**RDS Multi-AZ**

This is a clinical application. Patient data and classification records must not be lost due to an AZ failure. Multi-AZ is on by default in the Terraform config and can be disabled via `var.multi_az = false` for dev environments to save cost.

**Separate KMS keys per service**

RDS, S3, and Secrets Manager each have their own KMS Customer Managed Key. This follows the principle of least privilege at the encryption layer: a compromise of the S3 key does not expose RDS data. Key rotation is enabled on all three.

**S3 versioning**

VCF files are clinical source data. Versioning provides a recovery path if a file is overwritten or accidentally deleted, and supports NHS data retention requirements. A lifecycle rule transitions objects to Glacier after one year to manage storage cost.

**Lambda DLQ + CloudWatch alarm**

Ingest failure is clinically significant: a VCF that silently fails to ingest means variants are missing from the analyst's view without any indication. The Lambda is configured with an SQS dead-letter queue. A CloudWatch alarm fires immediately when any message lands on the DLQ, notifying the configured email address. Failed events can be replayed from the DLQ once the underlying issue is resolved.

**VPC endpoints**

The Lambda and ECS tasks need to reach S3 and Secrets Manager. Without VPC endpoints, this traffic routes out through the NAT Gateway, incurring data transfer costs and adding a network hop. The S3 Gateway endpoint (free) and Secrets Manager Interface endpoint keep this traffic inside the AWS network.

---

### Secrets management

The RDS password is generated by Terraform (`random_password`), stored in Secrets Manager (KMS-encrypted), and never written to any file or environment variable in plain text. The ECS task and Lambda both receive `DB_SECRET_ARN` as an environment variable and fetch the credentials at startup via the Secrets Manager SDK. The application constructs `DATABASE_URL` from the fetched secret.

This means rotating the database password requires only a Secrets Manager update — no redeployment, no `.env` file changes.

---

### Audit log

The `audit_log` table records every classification action, workflow status change, and ingest event with the old and new values as JSONB. This is a requirement for clinical governance: a lab must be able to demonstrate what classification was in effect at any point in time, who made it, and what changed.

The audit log is append-only. Records are never updated or deleted. The `occurred_at` timestamp uses `TIMESTAMPTZ` (not `TIMESTAMP`) to avoid ambiguity across timezone changes.

---

## Schema

```
patients
  └─ samples (one patient → many samples over time)
       ├─ variants (one sample → many variants)
       │    └─ variant_classification (one active classification per variant)
       │         └─ classification_criterion (one row per ACGS/SVIG criterion)
       └─ workflow (one status record per sample)

audit_log (append-only log of all mutations)
```

**Key constraints:**

- `patients.lab_number` — `UNIQUE NOT NULL`. The lab record number is the primary patient identifier. NHS number is optional (some referrals arrive without one).
- `samples.s3_key` — `UNIQUE NOT NULL`. Enforces one sample per VCF file. Also the key for idempotent re-ingest.
- `variant_classification.deleted_at` — soft delete. Classifications are never hard-deleted; resets set `deleted_at` to preserve audit history.

---

## Classification frameworks

### ACGS 2024 SNV/indel (germline)

Implements the ACGS Best Practice Guidelines for Variant Classification (2024 edition), which supersede the 2020 guidelines. Criteria are defined in `config/acgs-snv-criteria.json`.

PP5 and BP6 are **not included**. Current ACGS guidance explicitly deprecates these codes (they encouraged circular reasoning via ClinVar submissions that themselves cited the same database).

CanVIG-UK is not a separate framework — it is ACGS SNV with gene-specific MTAF overrides for the BA1 and BS1 criteria. The framework stored in the database is always `acgs_snv`; the CanVIG distinction is captured in the pre-computed value string (e.g. `"MTAF = 0.001 [CanVIG BRCA1]"`).

### SVIG-UK (somatic)

Implements the SVIG-UK somatic variant classification framework. Criteria are defined in `config/svig-criteria.json`.

Notable differences from ACGS:
- O1 (canonical oncogenic) and B1 (germline polymorphism) are standalone classifiers — they override the point score entirely.
- B2 forces VUS regardless of score.
- Oncogenic/Likely Oncogenic replaces Pathogenic/Likely Pathogenic.

### Scoring

Both frameworks use the Tavtigian point-based system:

| Strength | Pathogenic points | Benign points |
|----------|:-----------------:|:-------------:|
| Very Strong | +8 | — |
| Strong | +4 | −4 |
| Moderate | +2 | −2 |
| Supporting | +1 | −1 |

ACGS thresholds: ≥10 Pathogenic · 6–9 Likely Pathogenic · 0–5 VUS · −1 to −6 Likely Benign · ≤−7 Benign

SVIG thresholds: identical, with Oncogenic/Likely Oncogenic replacing Pathogenic/Likely Pathogenic.

---

## Project structure

```
app/                        Next.js App Router pages and API routes
  page.tsx                  Patient list
  patients/[id]/            Patient detail + variant table
  patients/[id]/variants/   Classification panel
  upload/                   VCF upload form
  api/                      API routes (variants, classification, workflow, ingest)

lib/                        Shared server-side logic
  db.ts                     PostgreSQL pool + transaction helpers
  vcf-parser.ts             Streaming VCF parser (VEP CSQ + SnpEff ANN)
  fhir-manifest.ts          FHIR R4 Bundle read/write + NHS number validation
  ingest.ts                 Core ingest logic (shared by Lambda + API route)
  pipeline-config.ts        Pipeline preset loader
  pre-compute-criteria.ts   Criteria suggestions from VCF annotations
  classification-engine.ts  Pure scoring functions (ACGS + SVIG)

lambda/
  ingest-handler.ts         Lambda entry point (calls lib/ingest.ts)

config/
  pipelines.yaml            Pipeline definitions and filter presets
  acgs-snv-criteria.json    ACGS 2024 criteria definitions + combination rules
  svig-criteria.json        SVIG-UK criteria definitions + combination rules
  canvig-gene-mtaf.json     CanVIG gene-specific BA1/BS1 thresholds
  manifest-schema.json      JSON Schema for FHIR R4 Bundle manifest

migrations/                 Plain SQL migration files (run in order)
terraform/                  All AWS infrastructure as Terraform
scripts/migrate.js          Migration runner
```

---

## Known limitations and future work

**VCF size limit.** Lambda has a 15-minute timeout. Batch-inserting 1,000 variants at a time, this handles exomes comfortably. Whole-genome VCFs (5–10 million variants) would exceed the timeout. The fix is an ECS batch task triggered by the S3 event instead of Lambda — the same `lib/ingest.ts` code would run there unchanged.

**No CNV classification.** Copy number variant classification uses a different ACGS framework (three-tier: pathogenic/uncertain/benign, with different evidence categories). It is architecturally separate from SNV/indel classification and is out of scope for this module.

**`evidence_links` is a flat array.** Classification criteria store evidence links as `TEXT[]` in PostgreSQL. This is sufficient when links are added and the full array is replaced on each save. If individual link metadata (label, added-by, added-at) becomes necessary, the path is a normalised `evidence_link (id, criterion_id, url, label, added_by, added_at)` table — a non-breaking migration.

**No report generation.** Producing a clinical report PDF from a confirmed classification is a common next step. This module does not implement it. The confirmed classification and all criteria are available in the database for a reporting module to consume.

**Authentication is external.** This module assumes the surrounding system handles authentication and provides a user identity. The `user_id` field in the audit log and classification records is populated from whatever the calling context provides — currently a string, intended to be replaced with the authenticated user's identifier from the broader system's auth middleware.
