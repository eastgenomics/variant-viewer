# build-prompt — variant-viewer API layer (PRs 6 & 7)

You are building the FastAPI route layer for the Variant Viewer application.
PRs 2–5 are complete. You are implementing PRs 6 and 7: authentication
middleware, read-only API routes, and write API routes.

## Your task

- **PR 6** — API key middleware + all read-only endpoints (patients, samples,
  variants, config). Also adds `run_in_transaction()` helper to `db.py`.
- **PR 7** — Write endpoints: presigned S3 URL generation, manual ingest
  trigger, workflow status transitions, classification score/persist/reset.

## Before writing any code

Read the following four files **in full, in order**:

1. `specification/api/README.md` — scope, layout, branch strategy, non-goals
2. `specification/api/DESIGN.md` — module responsibilities, route catalogue,
   request/response shapes, DB query patterns, auth design, workflow state machine
3. `specification/api/IMPLEMENTATION.md` — TDD milestones M14–M18 with full
   test code and implementation patterns
4. `specification/api/REFERENCE.md` — env vars, complete request/response
   examples, SQL reference, audit log action strings

Also confirm the PRs 2–5 spec is available at `specification/DESIGN.md` — you
will need to understand `db.query`, `db.with_transaction`, `classify()`,
`ingest_sample()`, and `DuplicateSubmissionError`.

## Build rules

1. **TDD strictly** — for each milestone, write the test file first. Run it.
   Confirm it fails (`ImportError` or `AttributeError`). Then implement the
   module. Run tests again. Confirm all pass. Do not skip the red step.
2. **PR 6 commits M14 + M15** (`auth`, `db.py` addition, all read routes,
   `main.py` update). PR 7 commits M16 + M17 + M18 (write routes, full suite).
3. **No AI attribution** in any commit message, comment, or docstring.
4. **Do not modify `app/lib/` modules** from PRs 2–5 except `db.py` (add
   `run_in_transaction` only). Do not touch `ingest.py`, `classification_engine.py`,
   `models.py`, etc.
5. **All DB calls in async handlers use `asyncio.to_thread`** — never call
   `db.query` or `db.run_in_transaction` directly without `await asyncio.to_thread(...)`.

## Milestone verification

| Milestone | Command | Expected |
|---|---|---|
| M14 | `cd backend && .venv/bin/pytest tests/test_auth.py -v` | All passed |
| M15 | `cd backend && .venv/bin/pytest tests/test_routes_read.py -v` | All passed |
| M16 | `cd backend && .venv/bin/pytest tests/test_routes_write.py -v` | All passed |
| M17 | `cd backend && .venv/bin/pytest tests/test_routes_classification.py -v` | All passed |
| M18 | `cd backend && .venv/bin/pytest --cov=app --cov-fail-under=80` | All passed, ≥80% |

Also after M18:
```bash
cd backend && .venv/bin/pytest tests/test_config_integrity.py -v
# Expected: 81 passed (pre-existing, unchanged)
```

## Invariants

### Invariant 1 (inherited) — No credentials in logs or exceptions

Same as PRs 2–5. `auth.py` must not log the resolved `API_KEY` value.
`db.py` changes must not introduce new credential logging.

```bash
cd backend && .venv/bin/pytest -s 2>&1 | \
  grep -iE "password|api_key|secret_string" && \
  echo "FAIL: credential leaked" || echo "OK"
```

### Invariant 2 — Auth not applied to `/api/health`

`GET /api/health` must return 200 without `X-API-Key`.
Every other `GET`, `POST`, `PUT`, `DELETE` route must return 401 without the header.

```bash
# Verify health is public
curl -s http://localhost:8000/api/health | grep '"status":"ok"'

# Verify patients is protected
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/patients
# Expected: 401
```

### Invariant 3 — All writes produce an audit_log entry

Every `PUT /api/workflow/`, `PUT /api/variants/.../classification`, and
`DELETE /api/variants/.../classification/...` must execute an
`INSERT INTO audit_log ...` within the same transaction.

Verified by `test_workflow_update_success`, `test_classify_persist_locks_classification`,
and `test_classify_reset_soft_deletes_and_creates_blank` tests, which assert that
the SQL executed on the mock connection includes `"INSERT INTO audit_log"`.

### Invariant 4 — Workflow transitions are validated before any DB write

`PUT /api/workflow/{sample_id}` must check the current status and validate
the transition **before** any `UPDATE` statement is executed. An invalid
transition must return `HTTP 422` without touching the DB.

Verified by `test_workflow_invalid_transition_returns_422`.

### Invariant 5 — Score-only classify endpoint makes no DB writes

`POST /api/variants/{variant_id}/classify` must call `classify()` and return
the result without calling `db.query`, `db.run_in_transaction`, or
`asyncio.to_thread`.

Verified by `test_classify_score_only_no_persist`, which asserts that
`db.run_in_transaction` is never called.

### Invariant 6 — Classification persist always soft-deletes before inserting

`PUT /api/variants/{variant_id}/classification` must always execute
`UPDATE variant_classification SET deleted_at=NOW() WHERE variant_id=%s AND deleted_at IS NULL`
before inserting the new record, even when no active classification exists
(the UPDATE is a no-op in that case). This prevents the partial-unique-index
constraint from being violated on concurrent requests.

Verified by `test_classify_persist_soft_deletes_existing`.

### Invariant 7 — `classification.py` must import `Framework` and `Strength` from `app.lib.models`

`ClassifyRequest`, `ClassificationSubmitRequest`, and `AppliedCriterionRequest` use
`Framework` and `Strength` type aliases. Import from `app.lib.models` (the canonical
shared location), not from `app.lib.classification_engine` (where they are also defined
but intended for internal use).

```python
# routes/classification.py
from app.lib.models import Framework, Strength
```

### Invariant 8 — Patch paths must target where the name is *used*, not where it is defined

Python mocking rule: when a module does `from x import name`, patching `x.name`
does **not** affect the importing module. You must patch `importing_module.name`.

This applies specifically to `routes/ingest.py`:
```python
# routes/ingest.py does: from app.lib.ingest import ingest_sample
# Therefore patch:
patch("app.routes.ingest.ingest_sample", ...)   # ✅ correct
patch("app.lib.ingest.ingest_sample", ...)      # ❌ wrong — doesn't affect routes/ingest.py
```

`db.run_in_transaction` is accessed as `db.run_in_transaction` (via module reference),
so patching `app.lib.db.run_in_transaction` **does** work correctly in all route tests.

### Invariant 9 — Always use `with conn.cursor() as c:` inside `_do` functions

All write route `_do(conn)` lambdas/functions must open cursors as context managers:
```python
def _do(conn):
    with conn.cursor() as c:   # ✅ cursor closed on exit
        c.execute(...)
        c.execute(...)
```
Never `c = conn.cursor()` without the context manager — the cursor will not be
explicitly closed, which wastes server-side resources.

1. Show the output of:
   ```bash
   find backend/app/middleware backend/app/routes -type f 2>/dev/null | sort
   # Expected: backend/app/routes/__init__.py only
   ```
2. Confirm all four spec documents have been read.
3. Proceed M14 → M18 in order. Do not skip the red (failing test) step.
