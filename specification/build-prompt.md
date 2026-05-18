# build-prompt — variant-viewer backend core (PRs 2–5)

You are building the Python backend core modules for the Variant Viewer FastAPI
application. This is a port of an existing TypeScript implementation to Python.

## Your task

Build PRs 2–5 of the Option A refactor (FastAPI + React SPA). PRs 2–4 port the
business-logic layer. PR 5 migrates the VCF parser to `cyvcf2`, adds the
`ingest_sample()` orchestration function, and adds the Lambda handler.
The source of truth for classification logic is the TypeScript implementation
on the `discovery/nextjs` branch. The Python port must produce **identical**
classification scores, labels, and warnings for the same inputs, verified by
golden-output test fixtures.

## Before writing any code

Read the following four files **in full, in order**:

1. `specification/README.md` — project layout, scope, non-goals
2. `specification/DESIGN.md` — architecture, module responsibilities (including
   numbered step-by-step algorithms), data models, error strategy
3. `specification/IMPLEMENTATION.md` — complete TDD milestones with all test
   and implementation code
4. `specification/REFERENCE.md` — env vars, config schemas, FHIR structure,
   golden fixture schema, classification scoring tables

After reading, show the current file tree of `backend/app/lib/` and
`backend/tests/` before writing any code.

## Build rules

1. **TDD strictly**: for each milestone, write the test file first. Run it.
   Confirm it fails (ImportError or AssertionError). Then implement the module.
   Run tests again. Confirm all pass. Do not skip the red step.
2. **One PR per milestone group**: commit at the end of each PR group
   (M2+M3 = PR 2 commit, M4+M5+M6 = PR 3 commit, M7+M8+M9 = PR 4 commit).
3. **No AI attribution** in any commit message, comment, or docstring.
4. **Milestone 7 (golden fixtures) must be committed before implementing M8**.
   The golden JSON files are the specification for the classification engine.
   Do not write `classification_engine.py` until the fixtures exist on disk.

## Milestone verification table

| Milestone | Verification command | Expected |
|---|---|---|
| M1 | `cd backend && .venv/bin/pytest tests/test_scaffold.py -v` | 2 passed |
| M2 | `cd backend && .venv/bin/pytest tests/test_models.py -v` | All passed |
| M3 | `cd backend && .venv/bin/pytest tests/test_pipeline_config.py -v` | All passed |
| M4 | `cd backend && .venv/bin/pytest tests/test_fhir_manifest.py -v` | All passed |
| M5 | `cd backend && .venv/bin/pytest tests/test_vcf_parser.py -v` | All passed |
| M6 | `cd backend && .venv/bin/pytest tests/test_db.py -v` | All passed |
| M7 | `cd backend && ls tests/golden/*.json \| wc -l` | 4 |
| M8 | `cd backend && .venv/bin/pytest tests/test_classification_engine.py -v` | All golden cases passed |
| M9 | `cd backend && .venv/bin/pytest tests/test_pre_compute_criteria.py -v` | All golden cases passed |
| M10 | `cd backend && .venv/bin/pytest --cov=app --cov=classification_engine --cov=pre_compute_criteria --cov-fail-under=80` | All passed, coverage ≥80% |
| M11 | `cd backend && .venv/bin/pytest tests/test_vcf_parser.py -v` | All 8 tests passed with cyvcf2 |
| M12 | `cd backend && .venv/bin/pytest tests/test_ingest.py -v` | All ingest_sample tests passed |
| M13 | `cd backend && .venv/bin/pytest -v --cov=app --cov-fail-under=80 && sg docker -c 'docker build -t vv-pr5 .'` | All passed, coverage ≥80%, Docker build succeeds |

Also verify after M10 that the pre-existing config integrity tests still pass:
```bash
cd backend && .venv/bin/pytest tests/test_config_integrity.py -v
# Expected: 81 passed (unchanged)
```

---

## Invariants

### Invariant 1 — Credentials must never appear in logs or exceptions

`db.py` resolves database credentials from Secrets Manager. The resolved
`DATABASE_URL`, individual credential fields (`username`, `password`), and the
Secrets Manager response body must **never** appear in any log output, print
statement, exception message, or test output.

**Verification:**
```bash
cd backend && .venv/bin/pytest -s 2>&1 | \
  grep -iE "password|secret_string|DATABASE_URL" && \
  echo "FAIL: credential leaked" || echo "OK"
```

### Invariant 2 — Classification outputs must match TypeScript golden fixtures exactly

The `classify()` function must return the **exact same `score` (int) and
`classification` (str) and `warnings` (list[str])** for each golden test case.
No rounding, no off-by-one on threshold boundaries.

Threshold boundaries (from DESIGN.md §3.6):
- score ≥ 10 → Pathogenic (not Likely\_Pathogenic at exactly 10)
- score ≥ 6 → Likely\_Pathogenic (not VUS at exactly 6)
- score ≥ 0 → VUS (not Likely\_Benign at exactly 0)
- score ≥ −6 → Likely\_Benign (not Benign at exactly −6)

**Verification:**
```bash
cd backend && .venv/bin/pytest tests/test_classification_engine.py -v --tb=short
# All parametrized golden cases must pass
```

### Invariant 3 — `applied=False` criteria must never affect the score

In `classify()`, only criteria where `applied == True` contribute to the score.
The `criteria` list may contain unapplied (suggested, pre-computed) criteria
that must be silently ignored.

**Verification:** The test `test_not_applied_criteria_ignored` in
`test_classification_engine.py` covers this case. It must pass.

### Invariant 4 — `pre_compute_criteria()` must never set `applied=True`

All `PreComputedCriterion` objects returned by `pre_compute_criteria()` are
suggestions. The `applied` flag does not exist on `PreComputedCriterion`
(by design — it's not a field). The downstream ingest layer creates
`ClassificationCriterion` rows with `applied=False` for all pre-computed
suggestions.

**Verification:**
```bash
cd backend && python -c "
from pre_compute_criteria import PreComputedCriterion
import dataclasses
fields = {f.name for f in dataclasses.fields(PreComputedCriterion)}
assert 'applied' not in fields, f'applied field found on PreComputedCriterion: {fields}'
print('OK: applied not a field on PreComputedCriterion')
"
```

### Invariant 5 — `pipeline_config.py` must resolve paths relative to the module file

The YAML config path must be computed as:
```python
Path(__file__).parent.parent.parent / "config" / "pipelines.yaml"
```

Never use `os.getcwd()` or relative paths like `"config/pipelines.yaml"` — this
breaks when pytest is run from a directory other than `backend/`.

**Verification:**
```bash
cd /tmp && python -c "
import sys; sys.path.insert(0, '/path/to/variant-viewer/backend')
from app.lib.pipeline_config import get_pipeline_keys
assert 'dragen_germline' in get_pipeline_keys()
print('OK: path resolution works from any cwd')
"
```

### Invariant 6 — `ingest_sample()` must check idempotency before any DB write

The idempotency check (`check_idempotency()`) must run **before** the first
`INSERT INTO patients` statement. Any DB write that executes before the
idempotency check creates a risk of leaving orphaned rows on failure.

**Verification:** `test_ingest_exact_duplicate` in `tests/test_ingest.py` confirms
that `DuplicateSubmissionError` is raised before any `INSERT` statement is executed
on the mock cursor.

### Invariant 7 — `ingest_sample()` must never swallow `jsonschema.ValidationError`

If the manifest JSON does not satisfy `manifest-schema.json`, `jsonschema.validate()`
raises `ValidationError`. This exception must propagate to the Lambda handler,
which translates it to a `{"statusCode": 400}` response. Catching and hiding
this error would allow malformed manifests into the DB.

**Verification:** `test_ingest_schema_validation_failure` in `tests/test_ingest.py`
confirms `jsonschema.ValidationError` is raised without being caught.

---

## Starting instruction

1. Show the output of:
   ```bash
   find backend/app/lib backend/tests -type f | sort
   ```
2. Show the content of `backend/app/lib/__init__.py` (if it exists).
3. Confirm all four spec documents have been read.
4. Proceed through milestones M1 → M13 in order. Do not skip the red
   (failing test) step for any milestone.
