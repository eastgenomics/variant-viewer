# Build prompt — variant-viewer frontend SPA (PRs 8–11)

You are building the React SPA frontend for the variant-viewer project.
The specification lives at `specification/frontend/` in the repo root.

## Before writing any code

Read the following four files **in full, in order**:

1. `specification/frontend/README.md` — what the SPA does, project layout, non-goals
2. `specification/frontend/DESIGN.md` — component architecture, module responsibilities, styling, testing strategy
3. `specification/frontend/IMPLEMENTATION.md` — milestone-by-milestone TDD build plan (M19–M26) with full code sketches
4. `specification/frontend/REFERENCE.md` — API endpoint catalogue, env vars, CSS classes, pipeline config schema, glossary

After reading, show the current file tree of `frontend/src/` and the contents
of `frontend/package.json`, then proceed milestone by milestone.

## Build rules

- **TDD for all library and component code**: write the test file first, verify it fails (or runs with 0 tests), then implement until green.
- **Commit at each milestone** with the message format: `feat(frontend): M<N> — <short description>`.
- **No AI attribution** in any commit message, comment, or file.
- **Never `npm install` globally** — all deps go in `frontend/package.json`.
- The reference implementation is `git show origin/discovery/nextjs:<path>` — read it before implementing any component.
- Copy config JSON files from backend: `cp backend/config/acgs-snv-criteria.json frontend/src/config/` and likewise for `svig-criteria.json`.

## Milestone verification table

| M | Description | Verification command | Expected |
|---|---|---|---|
| M_pre1–8 | Backend extensions | `cd backend && .venv/bin/pytest -q --tb=no` | All 260+ tests green |
| M19 | Scaffold | `cd frontend && npm ci && npm run build && npm test` | Build succeeds; 0 tests |
| M20 | `display-utils.ts` | `cd frontend && npm test -- display-utils` | All display-utils tests green |
| M21 | `classification-engine.ts` | `cd frontend && npm test -- classification-engine` | All 4 golden cases green |
| M22 | `api.ts` | `cd frontend && npm test -- api.test` | All API wrapper tests green |
| M23 | Shared components | `cd frontend && npm test -- WorkflowBadge ClassificationBadge PatientListTable PatientHeader` | All render tests green |
| M24 | Specimen + variant components | `cd frontend && npm test -- SpecimenCard WorkflowControl VariantTable` | All tests green |
| M25 | Classification panel | `cd frontend && npm test -- ClassificationPanel CriterionRow` | All panel tests green |
| M26 | Upload form + pages + full build | `cd frontend && npm test && npx tsc --noEmit && npm run build && docker build -t vv-frontend .` | All tests green; no TS errors; dist/ built; Docker image builds |

## Starting instruction

First, check whether the backend pre-requisite milestones (M_pre1–8) have already
been implemented by running `cd backend && .venv/bin/pytest -q --tb=no` and
checking the routes include DELETE endpoints, `POST /api/ingest-direct`, and
extended PatientSummary/VariantSummary fields. If not, implement M_pre1–8
before proceeding.

Then show `ls frontend/src/` and `cat frontend/package.json`, and proceed with
M19. Do not skip milestones or implement ahead of the current milestone's tests.

---

## Invariants

### Invariant 1 — No patient PII in the UI

The SPA must never display `patients.name` or `patients.nhs_number` in any
rendered component.

**Verification:**
```bash
grep -r "nhs_number" frontend/src/components/ frontend/src/pages/
# Expected: no output (comments only permitted)
```

### Invariant 2 — API key never logged

`api.ts` reads `VITE_API_KEY` from `import.meta.env`. The raw key value must
never appear in a `console.log`, `console.error`, error message string, or any
other output.

**Verification:**
```bash
grep -n "VITE_API_KEY" frontend/src/lib/api.ts
# Expected: only the line that assigns it to a header — no string interpolation, no log calls
```

### Invariant 3 — Evidence links are http/https only

`CriterionRow` must validate all user-entered evidence links before adding them
to state. Only `http:` and `https:` protocols are accepted. `javascript:`,
`data:`, and relative URLs must be rejected.

**Verification:**
`src/tests/CriterionRow.test.tsx` must include a test that asserts a
`javascript:` URL is rejected.

### Invariant 4 — Classification engine matches Python backend

The TypeScript `classify()` function must produce the same `score` and
`classification` for the four golden fixture inputs as `classification_engine.py`.
Port the algorithm exactly from `discovery/nextjs:lib/classification-engine.ts`;
do not simplify or modify scoring logic.

**Verification:**
M21 golden-case tests pass for all four inputs covering ACGS SNV (LP, VUS, Benign)
and SVIG (LP) cases.

### Invariant 5 — No direct database or S3 access from the SPA

All data operations go through the FastAPI REST API. The SPA must not import
`psycopg2`, `boto3`, or any database/AWS SDK.

**Verification:**
```bash
grep -r "psycopg2\|boto3\|pg\|postgres" frontend/src/
# Expected: no output
```
