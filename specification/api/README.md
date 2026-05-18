# variant-viewer API layer — PRs 6 & 7

Authentication middleware, read-only API routes, and write API routes for the
Variant Viewer FastAPI backend.

## What this build delivers

1. **PR 6 — Auth + read routes** — API key middleware and all read-only endpoints:
   patients, samples, variants, and classification config. Establishes the
   `asyncio.to_thread` DB-call pattern and TestClient mocking approach for all
   subsequent route PRs.
2. **PR 7 — Write routes** — Presigned S3 URL generation, manual ingest trigger,
   workflow status transitions, and classification submit/update/reset. All writes
   produce append-only audit log entries.

## Why two PRs, not one

Authentication (a critical clinical safety and compliance blocker) lands in PR 6.
Read routes are safe to review first — no DB writes, no S3 calls, no business logic
scoring. PR 7's write routes carry real complexity (presigned URL signing, the
`with_transaction` path, workflow state machine, and classification scoring + persistence)
and deserve dedicated review focus. Each PR is ~300–400 LoC + tests.

## Status of this document set

These documents are the **complete design and build specification** for PRs 6 and 7.
A fresh agent session or human developer should be able to read this directory and
implement both PRs without needing the original conversation.

Read in this order:

1. **README.md** (this file) — orientation, project layout, quick start
2. **DESIGN.md** — module responsibilities, route catalogue, request/response shapes,
   DB query patterns, auth design, audit log strategy, error handling
3. **IMPLEMENTATION.md** — TDD milestones M14–M18 with full Red/Green/Verify code
4. **REFERENCE.md** — env vars, request/response schemas, SQL reference, error shapes

## Project layout (target after PRs 6–7)

```text
backend/
├── app/
│   ├── main.py                         Updated — register all routers
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── auth.py                     PR 6 — API key resolution + FastAPI dependency
│   ├── routes/
│   │   ├── __init__.py                 (pre-existing, empty)
│   │   ├── health.py                   PR 6 — GET /api/health (extended)
│   │   ├── patients.py                 PR 6 — GET /api/patients, /api/patients/{id}
│   │   ├── samples.py                  PR 6 — GET /api/samples/{id}, /api/samples/{id}/variants
│   │   ├── variants.py                 PR 6 — GET /api/variants/{id}
│   │   ├── config.py                   PR 6 — GET /api/config/criteria/{framework}
│   │   ├── upload.py                   PR 7 — POST /api/upload-url
│   │   ├── ingest.py                   PR 7 — POST /api/ingest
│   │   ├── workflow.py                 PR 7 — PUT /api/workflow/{sample_id}
│   │   └── classification.py           PR 7 — POST/PUT/DELETE classification
│   └── lib/
│       ├── db.py                       Updated PR 6 — add run_in_transaction() helper
│       └── ...                         (pre-existing PRs 2–5 modules, unchanged)
├── tests/
│   ├── test_auth.py                    PR 6 — middleware tests
│   ├── test_routes_read.py             PR 6 — all read route tests
│   ├── test_routes_write.py            PR 7 — upload, ingest, workflow tests
│   ├── test_routes_classification.py   PR 7 — classification route tests
│   └── ...                             (pre-existing)
├── requirements.in                     (unchanged — no new deps)
└── requirements.txt                    (unchanged)
```

## No new Python dependencies

PRs 6 and 7 use only libraries already present in `requirements.txt`:
`fastapi`, `pydantic`, `boto3`, `psycopg2-binary`, `httpx`, `pytest`.

## Branch structure

| PR | Branch | Base |
|---|---|---|
| 6 | `feat/pr6-read-api` | `main` (after PR 5 merges) |
| 7 | `feat/pr7-write-api` | `feat/pr6-read-api` |

PR 7 is raised against `feat/pr6-read-api`. After PR 6 merges, PR 7 is rebased
onto `main` before merging.

## Quick start (once built)

```bash
cd backend

# Run all tests (no real DB needed)
.venv/bin/pytest tests/test_auth.py tests/test_routes_read.py tests/test_routes_write.py \
                 tests/test_routes_classification.py -v

# Run full suite including pre-existing tests
.venv/bin/pytest -v --cov=app --cov-report=term-missing

# Start locally (requires DATABASE_URL + API_KEY in env)
DATABASE_URL=postgresql://user:pass@localhost:5432/variants \
API_KEY=dev-key \
.venv/bin/uvicorn app.main:app --reload --port 8000
```

## Target user

A clinical bioinformatics developer building the Variant Viewer API layer. They
have completed PRs 2–5 and have working `db.py`, `models.py`, `classification_engine.py`,
`pre_compute_criteria.py`, and `ingest.py` modules. They need the FastAPI route
layer that exposes these modules over HTTP.

## Non-goals

- **No frontend components** — React SPA is PRs 8–11.
- **No Terraform / ECS changes** — infrastructure is PR 12.
- **No per-user authentication** — v0.1 uses a shared API key; per-user OIDC
  (via ALB) is a post-PR-12 roadmap item. User identity for audit log is
  asserted by the client in the request body.
- **No real-DB integration tests** — all route tests mock `db.query` and
  `db.run_in_transaction`. End-to-end tests against a real DB are PR 12.
- **No rate limiting or request tracing** — out of scope for v0.1.
