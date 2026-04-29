---
name: Python migration assessment
description: Feasibility and effort assessment for converting variant-viewer from Next.js/TypeScript to a Python web framework
type: project
---

Assessed 2026-04-25. Written to `docs/python-migration-assessment.md` and published as a Confluence page:
https://cuhbioinformatics.atlassian.net/wiki/spaces/DV/pages/4673994824/Python+Migration+Assessment

## Three options evaluated

- **Option A — FastAPI + React SPA (decoupled):** Replace Next.js back-end with FastAPI; keep React, re-host as static SPA via Vite. ~4–6 weeks. **Recommended.**
- **Option B — FastAPI + HTMX + Jinja2:** Full Python stack, no JS framework. ~10–16 weeks. High risk on ClassificationPanel UX.
- **Option C — Django full-stack:** As Option B but with Django ORM + migrations. ~10–16 weeks. Highest learning curve.

## Key findings

- Business logic (`lib/`) is the easiest layer to port — pure functions, natural Python analogues (`pysam`/`cyvcf2` for VCF parser, dataclasses for TS interfaces, `jsonschema` for `ajv`, `boto3` for AWS SDK).
- The classification engine (ACGS SNV, SVIG-UK) is pure numeric logic over JSON config — ideal Python candidate.
- ClassificationPanel.tsx (589 lines) is the dominant risk in Options B/C — live per-criterion score recalculation is hard to replicate idiomatically in HTMX.
- Infrastructure (ECS, RDS, Terraform, SQL migrations, JSON config files) is unchanged in all options.

## What does not change in any option

PostgreSQL schema, SQL migrations, Terraform, JSON config files, Docker Compose, domain/DNS/TLS, `config/pipelines.yaml`.

## Rationale for Option A

- Keeps risk in the right place (backend migrated, complex React UI preserved).
- React components are already almost Next.js-free.
- FastAPI: async, Pydantic, OpenAPI docs — well-suited to clinical API.
- Option A can evolve into Option B incrementally (replace React components with HTMX partials one at a time).
