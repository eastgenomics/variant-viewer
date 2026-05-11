# IMPLEMENTATION — variant-viewer API layer (PRs 6 & 7)

## 0. Prerequisites

```bash
# All PRs 2–5 modules must be present and tests green
cd backend
.venv/bin/pytest tests/ -q
# Expected: all existing tests pass (config integrity + models + db + vcf_parser +
#            fhir_manifest + classification_engine + pre_compute + ingest)

# Confirm starting file tree
find app/middleware app/routes -type f 2>/dev/null | sort
# Expected: app/routes/__init__.py only
```

---

## 1. Milestone plan

| M | PR | Module(s) | Red tests | Green when |
|---|---|---|---|---|
| M14 | 6 | `middleware/auth.py` + `db.py` addition | `test_auth.py` | Auth passes/fails correctly; `run_in_transaction` works |
| M15 | 6 | `routes/health.py`, `routes/patients.py`, `routes/samples.py`, `routes/variants.py`, `routes/config.py` + `main.py` update | `test_routes_read.py` | All read routes return correct shapes with mocked DB |
| M16 | 7 | `routes/upload.py`, `routes/ingest.py`, `routes/workflow.py` | `test_routes_write.py` | Upload URL generated; ingest delegates to `ingest_sample()`; workflow transitions enforced |
| M17 | 7 | `routes/classification.py` | `test_routes_classification.py` | Score-only; persist with lock; soft-delete + reset |
| M18 | 7 | Full suite | All tests | 100% of route tests + pre-existing tests green; coverage ≥80% |

---

## 2. Milestone 14 — Auth middleware + `db.run_in_transaction`

### Red: write `tests/test_auth.py`

```python
# tests/test_auth.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
import app.middleware.auth as auth_module


@pytest.fixture(autouse=True)
def reset_auth(monkeypatch):
    monkeypatch.setattr(auth_module, "_resolved_key", None)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key-123")
    with TestClient(app) as c:
        yield c


def test_health_no_auth_required(client):
    r = client.get("/api/health")
    assert r.status_code == 200


def test_protected_route_no_key_returns_401(client, monkeypatch):
    # Patch a simple protected route to exist for this test
    # In practice, /api/patients is protected — tested in M15
    # This test uses the auth dependency directly
    from fastapi import FastAPI, Depends
    from app.middleware.auth import require_api_key
    test_app = FastAPI()
    test_app.get("/ping", dependencies=[Depends(require_api_key)])(lambda: {"ok": True})
    with TestClient(test_app) as tc:
        monkeypatch.setenv("API_KEY", "secret-key-123")
        monkeypatch.setattr(auth_module, "_resolved_key", None)
        r = tc.get("/ping")
        assert r.status_code == 401


def test_protected_route_wrong_key_returns_401(client, monkeypatch):
    from fastapi import FastAPI, Depends
    from app.middleware.auth import require_api_key
    test_app = FastAPI()
    test_app.get("/ping", dependencies=[Depends(require_api_key)])(lambda: {"ok": True})
    with TestClient(test_app) as tc:
        monkeypatch.setenv("API_KEY", "secret-key-123")
        monkeypatch.setattr(auth_module, "_resolved_key", None)
        r = tc.get("/ping", headers={"X-API-Key": "wrong"})
        assert r.status_code == 401


def test_protected_route_correct_key_passes(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key-123")
    monkeypatch.setattr(auth_module, "_resolved_key", None)
    from fastapi import FastAPI, Depends
    from app.middleware.auth import require_api_key
    test_app = FastAPI()
    test_app.get("/ping", dependencies=[Depends(require_api_key)])(lambda: {"ok": True})
    with TestClient(test_app) as tc:
        r = tc.get("/ping", headers={"X-API-Key": "secret-key-123"})
        assert r.status_code == 200


def test_auth_resolves_from_secrets_manager(monkeypatch):
    import json
    from unittest.mock import MagicMock, patch
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("API_KEY_SECRET_ARN", "arn:aws:...:secret:api-key")
    monkeypatch.setattr(auth_module, "_resolved_key", None)

    mock_sm = MagicMock()
    mock_sm.get_secret_value.return_value = {
        "SecretString": json.dumps({"api_key": "sm-resolved-key"})
    }
    with patch("boto3.client", return_value=mock_sm):
        key = auth_module._get_api_key()
    assert key == "sm-resolved-key"


def test_auth_raises_if_neither_env_set(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("API_KEY_SECRET_ARN", raising=False)
    monkeypatch.setattr(auth_module, "_resolved_key", None)
    with pytest.raises(RuntimeError, match="API_KEY or API_KEY_SECRET_ARN"):
        auth_module._get_api_key()


def test_run_in_transaction_commits(monkeypatch):
    import app.lib.db as db_module
    from unittest.mock import MagicMock, patch
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.delenv("DB_SECRET_ARN", raising=False)
    db_module._reset_pool()

    mock_conn = MagicMock()
    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    with patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool):
        result = db_module.run_in_transaction(lambda conn: "done")
    assert result == "done"
    mock_conn.commit.assert_called_once()
```

### Green: create `app/middleware/__init__.py` and `app/middleware/auth.py`

```python
# app/middleware/__init__.py
# (empty)
```

```python
# app/middleware/auth.py
from __future__ import annotations

import json
import logging
import os

import boto3
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_resolved_key: str | None = None


def _get_api_key() -> str:
    global _resolved_key
    if _resolved_key:
        return _resolved_key

    arn = os.environ.get("API_KEY_SECRET_ARN")
    if arn:
        region = os.environ.get("AWS_REGION", "eu-west-2")
        sm = boto3.client("secretsmanager", region_name=region)
        resp = sm.get_secret_value(SecretId=arn)
        secret = json.loads(resp["SecretString"])
        _resolved_key = secret["api_key"]
    else:
        _resolved_key = os.environ.get("API_KEY")

    if not _resolved_key:
        raise RuntimeError("API_KEY or API_KEY_SECRET_ARN must be set")

    return _resolved_key


async def require_api_key(
    api_key: str | None = Security(_api_key_header),
) -> str:
    """FastAPI dependency: validates X-API-Key header. Raises HTTP 401 if absent or wrong."""
    if not api_key or api_key != _get_api_key():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key


def _reset_resolved_key() -> None:
    """Test helper — reset cached key between tests."""
    global _resolved_key
    _resolved_key = None
```

### Green: add `run_in_transaction` to `app/lib/db.py`

Add after the existing `with_transaction` definition:

```python
from collections.abc import Callable
from typing import TypeVar
T = TypeVar("T")

def run_in_transaction(fn: Callable[[psycopg2.extensions.connection], T]) -> T:
    """Run fn(conn) inside a transaction. Designed for asyncio.to_thread dispatch."""
    with with_transaction() as conn:
        return fn(conn)
```

**Verification:**
```bash
cd backend && .venv/bin/pytest tests/test_auth.py -v
# Expected: all tests green
```

---

## 3. Milestone 15 — Read routes

### Red: write `tests/test_routes_read.py`

```python
# tests/test_routes_read.py
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import app.middleware.auth as auth_module

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture(autouse=True)
def reset_auth(monkeypatch):
    monkeypatch.setattr(auth_module, "_resolved_key", None)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    from app.main import app
    with TestClient(app) as c:
        yield c


# ─── Health ───────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


# ─── Patients list ────────────────────────────────────────────────────────────

def test_patients_requires_auth(client):
    r = client.get("/api/patients")
    assert r.status_code == 401


def test_patients_list_empty(client, monkeypatch):
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [{"n": 0}]
        if "COUNT" in sql else [])
    r = client.get("/api/patients", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_patients_list_returns_items(client, monkeypatch):
    rows = [
        {"id": 1, "lab_number": "LAB-001", "name": "Jane Smith"},
        {"id": 2, "lab_number": "LAB-002", "name": "John Doe"},
    ]

    def mock_query(sql, params=()):
        if "COUNT" in sql:
            return [{"n": 2}]
        return rows

    monkeypatch.setattr("app.lib.db.query", mock_query)
    r = client.get("/api/patients", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    assert body["total"] == 2
    assert body["items"][0]["lab_number"] == "LAB-001"


def test_patients_list_pagination_params(client, monkeypatch):
    captured = {}
    def mock_query(sql, params=()):
        if "COUNT" in sql:
            return [{"n": 100}]
        captured["params"] = params
        return []
    monkeypatch.setattr("app.lib.db.query", mock_query)
    client.get("/api/patients?limit=10&offset=20", headers=HEADERS)
    assert 10 in captured["params"] and 20 in captured["params"]


def test_patients_list_limit_max_200(client, monkeypatch):
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [{"n": 0}]
        if "COUNT" in sql else [])
    r = client.get("/api/patients?limit=999", headers=HEADERS)
    assert r.status_code == 422   # FastAPI validation: limit ≤ 200


# ─── Patient detail ───────────────────────────────────────────────────────────

def test_patient_detail_not_found(client, monkeypatch):
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [])
    r = client.get("/api/patients/999", headers=HEADERS)
    assert r.status_code == 404


def test_patient_detail_returns_samples(client, monkeypatch):
    def mock_query(sql, params=()):
        if "FROM patients" in sql:
            return [{"id": 1, "lab_number": "LAB-001", "name": "Jane", "created_at": None}]
        if "FROM samples" in sql:
            return [
                {"id": 10, "name": "26041S0057", "case_type": "germline",
                 "pipeline_key": "dragen_germline", "ingested_at": None,
                 "workflow_status": "pending"},
            ]
        return []
    monkeypatch.setattr("app.lib.db.query", mock_query)
    r = client.get("/api/patients/1", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["lab_number"] == "LAB-001"
    assert len(body["samples"]) == 1
    assert body["samples"][0]["name"] == "26041S0057"


# ─── Sample detail ────────────────────────────────────────────────────────────

def test_sample_detail_not_found(client, monkeypatch):
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [])
    r = client.get("/api/samples/999", headers=HEADERS)
    assert r.status_code == 404


def test_sample_detail_returns_patient_and_workflow(client, monkeypatch):
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [{
        "id": 10, "name": "26041S0057", "s3_key": "runs/2024-11-05/26041S0057.vcf.gz",
        "case_type": "germline", "pipeline_key": "dragen_germline",
        "tissue": None, "sequencing_date": None, "ingested_at": None,
        "patient_id": 1, "lab_number": "LAB-001", "patient_name": "Jane",
        "workflow_status": "pending", "variant_count": 42,
    }])
    r = client.get("/api/samples/10", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "26041S0057"
    assert body["patient"]["lab_number"] == "LAB-001"
    assert body["workflow_status"] == "pending"
    assert body["variant_count"] == 42


# ─── Sample variant list ──────────────────────────────────────────────────────

def test_sample_variants_returns_list(client, monkeypatch):
    def mock_query(sql, params=()):
        if "COUNT" in sql:
            return [{"n": 1}]
        return [{
            "id": 100, "chrom": "1", "pos": 12345, "ref": "A", "alt": "G",
            "gene": "BRCA1", "consequence": "missense_variant",
            "gnomad_af": 0.0001, "revel_score": 0.75, "spliceai_max": 0.1,
            "classification": None, "score": None, "framework": None,
            "locked_at": None,
        }]
    monkeypatch.setattr("app.lib.db.query", mock_query)
    r = client.get("/api/samples/10/variants", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["gene"] == "BRCA1"


# ─── Variant detail ───────────────────────────────────────────────────────────

def test_variant_detail_not_found(client, monkeypatch):
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [])
    r = client.get("/api/variants/999", headers=HEADERS)
    assert r.status_code == 404


def test_variant_detail_includes_classification(client, monkeypatch):
    call_count = {"n": 0}
    def mock_query(sql, params=()):
        call_count["n"] += 1
        if call_count["n"] == 1:   # variant + case_type
            return [{"id": 100, "chrom": "1", "pos": 12345, "ref": "A", "alt": "G",
                     "gene": "BRCA1", "consequence": "missense_variant",
                     "hgvs_c": "c.100A>G", "hgvs_p": "p.Thr34Ala",
                     "gnomad_af": 0.0001, "revel_score": 0.75, "spliceai_max": 0.1,
                     "clinvar_sig": None, "info_json": {}, "case_type": "germline"}]
        if call_count["n"] == 2:   # active classification
            return [{"id": 50, "framework": "acgs_snv", "framework_version": "ACGS 2024",
                     "score": None, "classification": None,
                     "locked_at": None, "locked_by": None}]
        if call_count["n"] == 3:   # criteria
            return [{"id": 1, "criterion_code": "PM2", "applied": False, "strength": "supporting",
                     "notes": None, "evidence_links": [], "pre_computed": True,
                     "pre_computed_value": "gnomAD AF absent"}]
        return []
    monkeypatch.setattr("app.lib.db.query", mock_query)
    r = client.get("/api/variants/100", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["gene"] == "BRCA1"
    assert body["active_classification"]["framework"] == "acgs_snv"
    assert len(body["active_classification"]["criteria"]) == 1
    assert body["active_classification"]["criteria"][0]["criterion_code"] == "PM2"


def test_variant_detail_no_classification(client, monkeypatch):
    call_count = {"n": 0}
    def mock_query(sql, params=()):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [{"id": 100, "chrom": "1", "pos": 12345, "ref": "A", "alt": "G",
                     "gene": None, "consequence": None, "hgvs_c": None, "hgvs_p": None,
                     "gnomad_af": None, "revel_score": None, "spliceai_max": None,
                     "clinvar_sig": None, "info_json": {}, "case_type": "germline"}]
        return []   # no active classification
    monkeypatch.setattr("app.lib.db.query", mock_query)
    r = client.get("/api/variants/100", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["active_classification"] is None


# ─── Config criteria ─────────────────────────────────────────────────────────

def test_config_criteria_acgs_snv(client):
    r = client.get("/api/config/criteria/acgs_snv", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert "criteria" in body
    assert "combination_rules" in body
    codes = [c["code"] for c in body["criteria"]]
    assert "PVS1" in codes
    assert "BA1" in codes


def test_config_criteria_svig(client):
    r = client.get("/api/config/criteria/svig", headers=HEADERS)
    assert r.status_code == 200
    codes = [c["code"] for c in r.json()["criteria"]]
    assert "O1" in codes
    assert "B1" in codes


def test_config_criteria_invalid_framework(client):
    r = client.get("/api/config/criteria/unknown", headers=HEADERS)
    assert r.status_code == 400
```

### Green: implement route modules

**`app/routes/health.py`:**
```python
from fastapi import APIRouter
from app.main import app   # NOTE: import version from app directly
# or set version in a constant

router = APIRouter()

@router.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}
```

**`app/routes/patients.py`** (key implementation pattern — others follow the same shape):
```python
from __future__ import annotations
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from app.lib import db
from app.middleware.auth import require_api_key

router = APIRouter(prefix="/api/patients", dependencies=[Depends(require_api_key)])


class PatientSummary(BaseModel):
    id: int
    lab_number: str
    name: str | None

class SampleSummary(BaseModel):
    id: int
    name: str
    case_type: str
    pipeline_key: str | None
    ingested_at: datetime | None
    workflow_status: str | None

class PatientDetailResponse(PatientSummary):
    created_at: datetime | None = None
    samples: list[SampleSummary]

class PatientListResponse(BaseModel):
    items: list[PatientSummary]
    total: int
    limit: int
    offset: int


@router.get("", response_model=PatientListResponse)
async def list_patients(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None),
):
    where = ""
    base_params: tuple = ()
    if search:
        where = " WHERE lab_number ILIKE %s OR name ILIKE %s"
        base_params = (f"%{search}%", f"%{search}%")

    total_rows = await asyncio.to_thread(
        db.query,
        "SELECT COUNT(*) AS n FROM patients" + where,
        base_params,
    )
    total = total_rows[0]["n"]

    rows = await asyncio.to_thread(
        db.query,
        "SELECT id, lab_number, name FROM patients"
        + where
        + " ORDER BY lab_number LIMIT %s OFFSET %s",
        base_params + (limit, offset),
    )
    return PatientListResponse(
        items=[PatientSummary(**r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{patient_id}", response_model=PatientDetailResponse)
async def get_patient(patient_id: int):
    rows = await asyncio.to_thread(
        db.query,
        "SELECT id, lab_number, name, created_at FROM patients WHERE id = %s",
        (patient_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Patient not found")

    sample_rows = await asyncio.to_thread(
        db.query,
        """
        SELECT s.id, s.name, s.case_type, s.pipeline_key, s.ingested_at,
               COALESCE(w.status, 'pending') AS workflow_status
        FROM samples s
        LEFT JOIN workflow w ON w.sample_id = s.id
        WHERE s.patient_id = %s
        ORDER BY s.ingested_at DESC NULLS LAST
        """,
        (patient_id,),
    )
    return PatientDetailResponse(
        **rows[0],
        samples=[SampleSummary(**s) for s in sample_rows],
    )
```

**`app/routes/samples.py`** — two endpoints:
- `GET /api/samples/{sample_id}`: single JOIN query (see DESIGN §3.6), returns `SampleDetailResponse`
- `GET /api/samples/{sample_id}/variants`: paginated variant + classification JOIN (see DESIGN §3.6), returns `VariantListResponse`

**`app/routes/variants.py`** — one endpoint:
- `GET /api/variants/{variant_id}`: three sequential `db.query` calls (variant, classification, criteria), returns `VariantDetailResponse`

**`app/routes/config.py`:**
```python
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from app.middleware.auth import require_api_key

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
_FRAMEWORK_FILES = {
    "acgs_snv": _CONFIG_DIR / "acgs-snv-criteria.json",
    "svig": _CONFIG_DIR / "svig-criteria.json",
}

router = APIRouter(prefix="/api/config", dependencies=[Depends(require_api_key)])

@router.get("/criteria/{framework}")
async def get_criteria(framework: str):
    path = _FRAMEWORK_FILES.get(framework)
    if not path:
        raise HTTPException(status_code=400, detail=f"Unknown framework: {framework!r}")
    return json.loads(path.read_text())
```

**Update `app/main.py`** to register all PR 6 routers:
```python
from app.routes import health, patients, samples, variants, config
app.include_router(health.router)
app.include_router(patients.router)
app.include_router(samples.router)
app.include_router(variants.router)
app.include_router(config.router)
```

Remove the inline `@app.get("/api/health")` handler that currently exists in `main.py`.

**Verification:**
```bash
cd backend && .venv/bin/pytest tests/test_routes_read.py -v
# Expected: all tests green
```

---

## 4. Milestone 16 — Upload, ingest, and workflow routes

### Red: write `tests/test_routes_write.py`

```python
# tests/test_routes_write.py
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import app.middleware.auth as auth_module
from app.lib.ingest import DuplicateSubmissionError

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture(autouse=True)
def reset_auth(monkeypatch):
    monkeypatch.setattr(auth_module, "_resolved_key", None)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    from app.main import app
    with TestClient(app) as c:
        yield c


# ─── Upload URL ───────────────────────────────────────────────────────────────

def test_upload_url_returns_two_urls(client, monkeypatch):
    monkeypatch.setenv("VCF_BUCKET_NAME", "test-bucket")

    def fake_presigned(op, Params, ExpiresIn):
        return f"https://s3.example.com/{Params['Key']}?signed=1"

    mock_s3 = MagicMock()
    mock_s3.generate_presigned_url.side_effect = fake_presigned

    with patch("boto3.client", return_value=mock_s3):
        r = client.post("/api/upload-url",
                        json={"vcf_filename": "sample.vcf.gz", "run_date": "2024-11-05"},
                        headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert "vcf_url" in body and "manifest_url" in body
    assert body["vcf_key"] == "runs/2024-11-05/sample.vcf.gz"
    assert body["manifest_key"] == "runs/2024-11-05/sample.manifest.json"
    assert body["expires_in"] == 3600


def test_upload_url_defaults_run_date_to_today(client, monkeypatch):
    monkeypatch.setenv("VCF_BUCKET_NAME", "test-bucket")
    mock_s3 = MagicMock()
    mock_s3.generate_presigned_url.return_value = "https://url"
    with patch("boto3.client", return_value=mock_s3):
        r = client.post("/api/upload-url",
                        json={"vcf_filename": "sample.vcf.gz"},
                        headers=HEADERS)
    assert r.status_code == 200
    import re
    assert re.match(r"runs/\d{4}-\d{2}-\d{2}/", r.json()["vcf_key"])


def test_upload_url_rejects_non_vcf_filename(client, monkeypatch):
    monkeypatch.setenv("VCF_BUCKET_NAME", "test-bucket")
    r = client.post("/api/upload-url",
                    json={"vcf_filename": "sample.bam"},
                    headers=HEADERS)
    assert r.status_code == 400


# ─── Ingest ───────────────────────────────────────────────────────────────────

def test_ingest_success(client, monkeypatch):
    monkeypatch.setenv("VCF_BUCKET_NAME", "test-bucket")

    def mock_transaction(fn):
        mock_conn = MagicMock()
        return fn(mock_conn)

    with patch("app.lib.db.run_in_transaction", side_effect=mock_transaction), \
         patch("app.lib.ingest.ingest_sample", return_value=42):
        r = client.post("/api/ingest",
                        json={"vcf_s3_key": "runs/2024-11-05/s.vcf.gz",
                              "user_id": "analyst-1"},
                        headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["sample_id"] == 42


def test_ingest_duplicate_returns_409(client, monkeypatch):
    monkeypatch.setenv("VCF_BUCKET_NAME", "test-bucket")
    exc = DuplicateSubmissionError("Duplicate")
    exc.existing_sample_id = 5
    exc.duplicate_type = "exact"

    with patch("app.lib.ingest.ingest_sample", side_effect=exc):
        with patch("app.lib.db.run_in_transaction", side_effect=lambda fn: fn(MagicMock())):
            r = client.post("/api/ingest",
                            json={"vcf_s3_key": "runs/2024-11-05/s.vcf.gz",
                                  "user_id": "analyst-1"},
                            headers=HEADERS)
    assert r.status_code == 409


def test_ingest_bad_key_returns_400(client, monkeypatch):
    monkeypatch.setenv("VCF_BUCKET_NAME", "test-bucket")
    with patch("app.lib.ingest.ingest_sample", side_effect=ValueError("Unsupported VCF key format")):
        with patch("app.lib.db.run_in_transaction", side_effect=lambda fn: fn(MagicMock())):
            r = client.post("/api/ingest",
                            json={"vcf_s3_key": "runs/2024-11-05/s.bam",
                                  "user_id": "analyst-1"},
                            headers=HEADERS)
    assert r.status_code == 400


# ─── Workflow ─────────────────────────────────────────────────────────────────

def test_workflow_update_success(client, monkeypatch):
    monkeypatch.setattr("app.lib.db.query",
        lambda sql, params=(): [{"status": "pending"}] if "SELECT" in sql else [])

    executed_sqls: list[str] = []
    def fake_transaction(fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.execute.side_effect = lambda sql, p=(): executed_sqls.append(sql)
        mock_conn.cursor.return_value = mock_cursor
        return fn(mock_conn)
    monkeypatch.setattr("app.lib.db.run_in_transaction", fake_transaction)

    r = client.put("/api/workflow/10",
                   json={"status": "reviewing", "user_id": "analyst-1"},
                   headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "reviewing"
    assert any("UPDATE workflow" in s for s in executed_sqls)
    assert any("INSERT INTO audit_log" in s for s in executed_sqls)


def test_workflow_invalid_transition_returns_422(client, monkeypatch):
    monkeypatch.setattr("app.lib.db.query",
        lambda sql, params=(): [{"status": "pending"}])
    r = client.put("/api/workflow/10",
                   json={"status": "reported", "user_id": "analyst-1"},
                   headers=HEADERS)
    assert r.status_code == 422
    assert "pending" in r.json()["detail"] and "reported" in r.json()["detail"]


def test_workflow_sample_not_found(client, monkeypatch):
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [])
    r = client.put("/api/workflow/999",
                   json={"status": "reviewing", "user_id": "analyst-1"},
                   headers=HEADERS)
    assert r.status_code == 404
```

### Green: implement `routes/upload.py`, `routes/ingest.py`, `routes/workflow.py`

**`routes/upload.py`** (key implementation):
```python
import json, os, re
from datetime import datetime
import boto3
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.middleware.auth import require_api_key

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])

class UploadUrlRequest(BaseModel):
    vcf_filename: str
    run_date: str | None = None

class UploadUrlResponse(BaseModel):
    vcf_url: str
    manifest_url: str
    vcf_key: str
    manifest_key: str
    expires_in: int

@router.post("/upload-url", response_model=UploadUrlResponse)
async def get_upload_url(body: UploadUrlRequest):
    if not re.search(r'\.vcf(\.gz)?$', body.vcf_filename):
        raise HTTPException(status_code=400,
            detail=f"vcf_filename must end with .vcf or .vcf.gz: {body.vcf_filename!r}")

    bucket = os.environ.get("VCF_BUCKET_NAME")
    if not bucket:
        raise HTTPException(status_code=500, detail="VCF_BUCKET_NAME not configured")

    date_prefix = body.run_date or datetime.today().strftime("%Y-%m-%d")
    vcf_key = f"runs/{date_prefix}/{body.vcf_filename}"
    manifest_key = re.sub(r'\.vcf(\.gz)?$', '.manifest.json', vcf_key)

    region = os.environ.get("AWS_REGION", "eu-west-2")
    s3 = boto3.client("s3", region_name=region)

    vcf_url = s3.generate_presigned_url(
        "put_object", Params={"Bucket": bucket, "Key": vcf_key}, ExpiresIn=3600
    )
    manifest_url = s3.generate_presigned_url(
        "put_object", Params={"Bucket": bucket, "Key": manifest_key}, ExpiresIn=3600
    )
    return UploadUrlResponse(
        vcf_url=vcf_url, manifest_url=manifest_url,
        vcf_key=vcf_key, manifest_key=manifest_key, expires_in=3600,
    )
```

**`routes/ingest.py`:**
```python
import asyncio, json, os
import boto3
import jsonschema
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.lib import db
from app.lib.ingest import ingest_sample, DuplicateSubmissionError
from app.middleware.auth import require_api_key

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])

class IngestRequest(BaseModel):
    vcf_s3_key: str
    user_id: str

@router.post("/ingest")
async def manual_ingest(body: IngestRequest):
    bucket = os.environ.get("VCF_BUCKET_NAME", "")
    region = os.environ.get("AWS_REGION", "eu-west-2")
    s3 = boto3.client("s3", region_name=region)

    def _do(conn):
        return ingest_sample(body.vcf_s3_key,
                             _manifest_key(body.vcf_s3_key),
                             bucket, s3, conn)
    try:
        sample_id = await asyncio.to_thread(db.run_in_transaction, _do)
        return {"sample_id": sample_id}
    except DuplicateSubmissionError as exc:
        raise HTTPException(status_code=409,
            detail=f"Duplicate submission: {exc}")
    except (ValueError, jsonschema.ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _manifest_key(vcf_key: str) -> str:
    import re
    return re.sub(r'\.vcf(\.gz)?$', '.manifest.json', vcf_key)
```

**`routes/workflow.py`:**
```python
import asyncio, json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Literal
from app.lib import db
from app.middleware.auth import require_api_key

router = APIRouter(prefix="/api/workflow", dependencies=[Depends(require_api_key)])

VALID_TRANSITIONS: dict[str, list[str]] = {
    "pending":   ["reviewing", "archived"],
    "reviewing": ["reported", "archived"],
    "reported":  ["archived"],
    "archived":  [],
}

class WorkflowUpdateRequest(BaseModel):
    status: Literal["reviewing", "reported", "archived"]
    user_id: str

@router.put("/{sample_id}")
async def update_workflow(sample_id: int, body: WorkflowUpdateRequest):
    rows = await asyncio.to_thread(
        db.query,
        "SELECT status FROM workflow WHERE sample_id = %s",
        (sample_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Sample workflow not found")

    current = rows[0]["status"]
    if body.status not in VALID_TRANSITIONS[current]:
        raise HTTPException(status_code=422,
            detail=f"Invalid transition: {current} → {body.status}")

    def _do(conn):
        c = conn.cursor()
        c.execute(
            "UPDATE workflow SET status=%s, updated_at=NOW(), updated_by=%s "
            "WHERE sample_id=%s",
            (body.status, body.user_id, sample_id),
        )
        c.execute(
            "INSERT INTO audit_log (user_id, action, entity_type, entity_id, "
            "old_value, new_value) VALUES (%s,%s,%s,%s,%s,%s)",
            (body.user_id, "update_workflow", "workflow", sample_id,
             json.dumps({"status": current}), json.dumps({"status": body.status})),
        )

    await asyncio.to_thread(db.run_in_transaction, _do)
    return {"sample_id": sample_id, "status": body.status}
```

**Verification:**
```bash
cd backend && .venv/bin/pytest tests/test_routes_write.py -v
```

---

## 5. Milestone 17 — Classification routes

### Red: write `tests/test_routes_classification.py`

```python
# tests/test_routes_classification.py
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import app.middleware.auth as auth_module

HEADERS = {"X-API-Key": "test-key"}

@pytest.fixture(autouse=True)
def reset_auth(monkeypatch):
    monkeypatch.setattr(auth_module, "_resolved_key", None)

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    from app.main import app
    with TestClient(app) as c:
        yield c

_ACGS_CRITERIA_PAYLOAD = {
    "criteria": [
        {"criterion_code": "PVS1", "applied": True, "strength": "very_strong"},
        {"criterion_code": "PM2",  "applied": True, "strength": "supporting"},
    ],
    "framework": "acgs_snv",
    "combination_rules": [],
    "locked_by": "analyst-1",
    "user_id": "analyst-1",
}


def test_classify_score_only_no_persist(client, monkeypatch):
    """POST /classify returns score without writing to DB."""
    call_log: list[str] = []
    monkeypatch.setattr("app.lib.db.run_in_transaction",
        lambda fn: call_log.append("CALLED") or None)

    r = client.post("/api/variants/100/classify",
                    json={k: v for k, v in _ACGS_CRITERIA_PAYLOAD.items()
                          if k in ("criteria", "framework", "combination_rules")},
                    headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["score"] == 9
    assert body["classification"] == "Likely_Pathogenic"
    assert call_log == []   # no DB write


def test_classify_persist_locks_classification(client, monkeypatch):
    """PUT /classification persists and locks the record."""
    # Mock variant lookup for framework selection
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [
        {"id": 100, "case_type": "germline", "gene": "BRCA1"}
    ] if "FROM variants" in sql else [
        {"id": 50, "framework": "acgs_snv", "framework_version": "ACGS 2024",
         "score": None, "classification": None, "locked_at": None, "locked_by": None}
    ] if "variant_classification" in sql else [])

    inserted: list[dict] = []
    def fake_transaction(fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = (99,)  # new classification_id
        mock_cursor.execute.side_effect = lambda sql, p=(): inserted.append(sql)
        mock_conn.cursor.return_value = mock_cursor
        return fn(mock_conn)

    monkeypatch.setattr("app.lib.db.run_in_transaction", fake_transaction)

    r = client.put("/api/variants/100/classification",
                   json=_ACGS_CRITERIA_PAYLOAD, headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["score"] == 9
    assert body["classification"] == "Likely_Pathogenic"
    # Verify DB writes occurred
    assert any("INSERT INTO variant_classification" in s for s in inserted)
    assert any("INSERT INTO classification_criterion" in s for s in inserted)
    assert any("INSERT INTO audit_log" in s for s in inserted)


def test_classify_persist_soft_deletes_existing(client, monkeypatch):
    """PUT /classification soft-deletes any existing active classification first."""
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [
        {"id": 100, "case_type": "germline", "gene": "BRCA1"}
    ] if "FROM variants" in sql else [
        {"id": 50}   # existing active classification
    ] if "variant_classification" in sql else [])

    executed: list[str] = []
    def fake_transaction(fn):
        mock_conn = MagicMock()
        mc = MagicMock()
        mc.__enter__ = lambda s: s
        mc.__exit__ = MagicMock(return_value=False)
        mc.fetchone.return_value = (99,)
        mc.execute.side_effect = lambda sql, p=(): executed.append(sql)
        mock_conn.cursor.return_value = mc
        return fn(mock_conn)

    monkeypatch.setattr("app.lib.db.run_in_transaction", fake_transaction)

    client.put("/api/variants/100/classification",
               json=_ACGS_CRITERIA_PAYLOAD, headers=HEADERS)
    assert any("deleted_at" in s and "UPDATE" in s for s in executed)


def test_classify_reset_soft_deletes_and_creates_blank(client, monkeypatch):
    """DELETE /classification/{id} soft-deletes and inserts a blank replacement."""
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [
        {"id": 50, "variant_id": 100, "framework": "acgs_snv",
         "framework_version": "ACGS 2024"}
    ])

    executed: list[str] = []
    def fake_transaction(fn):
        mock_conn = MagicMock()
        mc = MagicMock()
        mc.__enter__ = lambda s: s
        mc.__exit__ = MagicMock(return_value=False)
        mc.fetchone.return_value = (51,)
        mc.execute.side_effect = lambda sql, p=(): executed.append(sql)
        mock_conn.cursor.return_value = mc
        return fn(mock_conn)

    monkeypatch.setattr("app.lib.db.run_in_transaction", fake_transaction)

    r = client.delete("/api/variants/100/classification/50",
                      json={"user_id": "analyst-1"}, headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["new_classification_id"] == 51
    assert any("deleted_at" in s for s in executed)
    assert any("INSERT INTO variant_classification" in s for s in executed)
    assert any("INSERT INTO audit_log" in s for s in executed)


def test_classify_reset_not_found(client, monkeypatch):
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [])
    r = client.delete("/api/variants/100/classification/999",
                      json={"user_id": "analyst-1"}, headers=HEADERS)
    assert r.status_code == 404
```

### Green: implement `routes/classification.py`

Three endpoints:

**`POST /api/variants/{variant_id}/classify`** (score only):
```python
@router.post("/{variant_id}/classify")
async def score_classification(variant_id: int, body: ClassifyRequest):
    # No DB needed — just call classify()
    from app.lib.classification_engine import classify, AppliedCriterion, CombinationRule
    criteria = [AppliedCriterion(**c.model_dump()) for c in body.criteria]
    rules = [CombinationRule(**r.model_dump()) for r in body.combination_rules]
    result = classify(criteria, body.framework, rules)
    return {"score": result.score, "classification": result.classification,
            "warnings": result.warnings}
```

**`PUT /api/variants/{variant_id}/classification`** (score + persist):
1. Load variant + `case_type` from DB (for audit context).
2. Call `classify()` to get score + classification.
3. In `run_in_transaction`:
   - `UPDATE variant_classification SET deleted_at=NOW() WHERE variant_id=%s AND deleted_at IS NULL`
   - `INSERT INTO variant_classification (..., score, classification, locked_at, locked_by) VALUES (...) RETURNING id`
   - For each criterion: `INSERT INTO classification_criterion (...) VALUES (...)`
   - `INSERT INTO audit_log (...)`
4. Return `ClassificationSubmitResponse` with score, classification, new `classification_id`.

**`DELETE /api/variants/{variant_id}/classification/{classification_id}`** (soft-delete + blank):
1. Load existing classification from DB; 404 if not found or `deleted_at IS NOT NULL`.
2. In `run_in_transaction`:
   - `UPDATE variant_classification SET deleted_at=NOW() WHERE id=%s`
   - `INSERT INTO variant_classification (variant_id, framework, framework_version) VALUES (%s,%s,%s) RETURNING id`
   - `INSERT INTO audit_log (... action='reset_classification' ...)`
3. Return `{"new_classification_id": int}`.

**Register in `app/main.py`:**
```python
from app.routes import upload, ingest, workflow, classification
app.include_router(upload.router)
app.include_router(ingest.router)
app.include_router(workflow.router)
app.include_router(classification.router)
```

**Verification:**
```bash
cd backend && .venv/bin/pytest tests/test_routes_classification.py -v
```

---

## 6. Milestone 18 — Full suite

```bash
cd backend

# All tests green
.venv/bin/pytest -v

# Coverage ≥80%
.venv/bin/pytest --cov=app --cov-report=term-missing --cov-fail-under=80

# Pre-existing config integrity tests still pass (unchanged)
.venv/bin/pytest tests/test_config_integrity.py -v
# Expected: 81 passed
```

**Acceptance criteria before PR 7 merge:**

- [ ] All pre-existing 81 config integrity tests pass (unchanged)
- [ ] All PR 6 tests pass: `test_auth.py`, `test_routes_read.py`
- [ ] All PR 7 tests pass: `test_routes_write.py`, `test_routes_classification.py`
- [ ] `GET /api/health` returns 200 without `X-API-Key`
- [ ] All other routes return 401 without `X-API-Key`
- [ ] `POST /api/variants/{id}/classify` returns correct score without DB write
- [ ] `PUT /api/variants/{id}/classification` soft-deletes existing + inserts new
- [ ] `DELETE /api/variants/{id}/classification/{id}` returns `new_classification_id`
- [ ] `PUT /api/workflow/{id}` with invalid transition returns 422
- [ ] Coverage ≥80% across `app/` modules
- [ ] No credential strings appear in test output (Invariant 1 from PRs 2–5)
