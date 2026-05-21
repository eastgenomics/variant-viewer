"""Tests for PR 7 write routes: upload-url, ingest, workflow."""
import json
import re
import pytest
import psycopg2.errors
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
    assert re.match(r"runs/\d{4}-\d{2}-\d{2}/", r.json()["vcf_key"])


def test_upload_url_rejects_non_vcf_filename(client, monkeypatch):
    monkeypatch.setenv("VCF_BUCKET_NAME", "test-bucket")
    r = client.post("/api/upload-url",
                    json={"vcf_filename": "sample.bam"},
                    headers=HEADERS)
    assert r.status_code == 400


def test_upload_url_rejects_path_traversal_filename(client, monkeypatch):
    monkeypatch.setenv("VCF_BUCKET_NAME", "test-bucket")
    r = client.post("/api/upload-url",
                    json={"vcf_filename": "../secret.vcf.gz"},
                    headers=HEADERS)
    assert r.status_code == 400


def test_upload_url_rejects_invalid_run_date(client, monkeypatch):
    monkeypatch.setenv("VCF_BUCKET_NAME", "test-bucket")
    r = client.post("/api/upload-url",
                    json={"vcf_filename": "sample.vcf.gz", "run_date": "not-a-date"},
                    headers=HEADERS)
    assert r.status_code == 400


def test_upload_url_rejects_semantically_invalid_run_date(client, monkeypatch):
    """A syntactically matching but semantically invalid date (e.g. month 13) returns 400."""
    monkeypatch.setenv("VCF_BUCKET_NAME", "test-bucket")
    r = client.post("/api/upload-url",
                    json={"vcf_filename": "sample.vcf.gz", "run_date": "2024-13-45"},
                    headers=HEADERS)
    assert r.status_code == 400


def test_upload_url_rejects_impossible_calendar_date(client, monkeypatch):
    """A date that looks plausible but is impossible (Feb 31) returns 400."""
    monkeypatch.setenv("VCF_BUCKET_NAME", "test-bucket")
    r = client.post("/api/upload-url",
                    json={"vcf_filename": "sample.vcf.gz", "run_date": "2026-02-31"},
                    headers=HEADERS)
    assert r.status_code == 400


def test_upload_url_missing_bucket_returns_500(client, monkeypatch):
    """VCF_BUCKET_NAME not set → 500 before any S3 call."""
    monkeypatch.delenv("VCF_BUCKET_NAME", raising=False)
    r = client.post("/api/upload-url",
                    json={"vcf_filename": "sample.vcf.gz"},
                    headers=HEADERS)
    assert r.status_code == 500
    assert "VCF_BUCKET_NAME" in r.json()["detail"]


def test_ingest_missing_bucket_returns_500(client, monkeypatch):
    """VCF_BUCKET_NAME not set → 500 before any S3/DB work."""
    monkeypatch.delenv("VCF_BUCKET_NAME", raising=False)
    r = client.post("/api/ingest",
                    json={"vcf_s3_key": "runs/2024-11-05/s.vcf.gz",
                          "user_id": "analyst-1"},
                    headers=HEADERS)
    assert r.status_code == 500
    assert "VCF_BUCKET_NAME" in r.json()["detail"]


def test_ingest_success(client, monkeypatch):
    monkeypatch.setenv("VCF_BUCKET_NAME", "test-bucket")

    executed_sqls: list[tuple] = []  # (sql, params) pairs

    def mock_transaction(fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.execute.side_effect = lambda sql, p=(): executed_sqls.append((sql, p))
        mock_conn.cursor.return_value = mock_cursor
        return fn(mock_conn)

    with patch("app.lib.db.run_in_transaction", side_effect=mock_transaction), \
         patch("app.routes.ingest.ingest_sample", return_value=42):
        r = client.post("/api/ingest",
                        json={"vcf_s3_key": "runs/2024-11-05/s.vcf.gz",
                              "user_id": "analyst-1"},
                        headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["sample_id"] == 42

    # Verify audit INSERT was called with the correct user_id and sample_id
    audit = next(
        ((s, p) for s, p in executed_sqls if "INSERT INTO audit_log" in s),
        None,
    )
    assert audit is not None, "Audit INSERT not found"
    _, audit_params = audit
    assert audit_params[0] == "analyst-1"  # user_id
    assert audit_params[1] == 42           # entity_id (sample_id)


def test_ingest_duplicate_returns_409(client, monkeypatch):
    monkeypatch.setenv("VCF_BUCKET_NAME", "test-bucket")
    exc = DuplicateSubmissionError("Duplicate", existing_sample_id=5, duplicate_type="exact")

    with patch("app.routes.ingest.ingest_sample", side_effect=exc):
        with patch("app.lib.db.run_in_transaction", side_effect=lambda fn: fn(MagicMock())):
            r = client.post("/api/ingest",
                            json={"vcf_s3_key": "runs/2024-11-05/s.vcf.gz",
                                  "user_id": "analyst-1"},
                            headers=HEADERS)
    assert r.status_code == 409


def test_ingest_unique_violation_returns_409(client, monkeypatch):
    """TOCTOU race: UniqueViolation from DB must map to 409, not 500."""
    monkeypatch.setenv("VCF_BUCKET_NAME", "test-bucket")
    with patch("app.routes.ingest.ingest_sample",
               side_effect=psycopg2.errors.UniqueViolation()):
        with patch("app.lib.db.run_in_transaction", side_effect=lambda fn: fn(MagicMock())):
            r = client.post("/api/ingest",
                            json={"vcf_s3_key": "runs/2024-11-05/s.vcf.gz",
                                  "user_id": "analyst-1"},
                            headers=HEADERS)
    assert r.status_code == 409


def test_ingest_bad_vcf_key_returns_400(client, monkeypatch):
    """Route-level VCF key check rejects non-.vcf/.vcf.gz keys before any S3/DB work."""
    monkeypatch.setenv("VCF_BUCKET_NAME", "test-bucket")
    r = client.post("/api/ingest",
                    json={"vcf_s3_key": "runs/2024-11-05/s.bam",
                          "user_id": "analyst-1"},
                    headers=HEADERS)
    assert r.status_code == 400


def test_ingest_invalid_manifest_returns_400(client, monkeypatch):
    """ValueError from ingest_sample (e.g. bad manifest) maps to 400."""
    monkeypatch.setenv("VCF_BUCKET_NAME", "test-bucket")
    with patch("app.routes.ingest.ingest_sample",
               side_effect=ValueError("Invalid manifest structure")):
        with patch("app.lib.db.run_in_transaction",
                   side_effect=lambda fn: fn(MagicMock())):
            r = client.post("/api/ingest",
                            json={"vcf_s3_key": "runs/2024-11-05/s.vcf.gz",
                                  "user_id": "analyst-1"},
                            headers=HEADERS)
    assert r.status_code == 400
    assert "Invalid manifest structure" in r.json()["detail"]


# ─── Workflow ─────────────────────────────────────────────────────────────────

def test_workflow_update_success(client, monkeypatch):
    monkeypatch.setattr("app.lib.db.query",
        lambda sql, params=(): [{"status": "pending"}] if "SELECT" in sql else [])

    executed_sqls: list[tuple] = []  # (sql, params) pairs

    def fake_transaction(fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 1
        mock_cursor.execute.side_effect = lambda sql, p=(): executed_sqls.append((sql, p))
        mock_conn.cursor.return_value = mock_cursor
        return fn(mock_conn)

    monkeypatch.setattr("app.lib.db.run_in_transaction", fake_transaction)

    r = client.put("/api/workflow/10",
                   json={"status": "reviewing", "user_id": "analyst-1"},
                   headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "reviewing"

    sqls = [s for s, _ in executed_sqls]
    assert any("UPDATE workflow" in s for s in sqls)
    assert any("INSERT INTO audit_log" in s for s in sqls)

    # Assert audit INSERT carries the correct user_id, sample_id, and status transition
    audit = next(
        ((s, p) for s, p in executed_sqls if "INSERT INTO audit_log" in s),
        None,
    )
    assert audit is not None, "Audit INSERT not found"
    _, audit_params = audit
    assert audit_params[0] == "analyst-1"                                    # user_id
    assert audit_params[3] == 10                                             # entity_id (sample_id)
    assert json.loads(audit_params[4]) == {"status": "pending"}             # old_value
    assert json.loads(audit_params[5]) == {"status": "reviewing"}           # new_value


def test_workflow_invalid_transition_returns_422(client, monkeypatch):
    monkeypatch.setattr("app.lib.db.query",
        lambda sql, params=(): [{"status": "pending"}])
    r = client.put("/api/workflow/10",
                   json={"status": "reported", "user_id": "analyst-1"},
                   headers=HEADERS)
    assert r.status_code == 422
    assert "pending" in r.json()["detail"] and "reported" in r.json()["detail"]


def test_workflow_concurrent_modification_returns_409(client, monkeypatch):
    """rowcount == 0 after UPDATE means a race; must return 409."""
    monkeypatch.setattr("app.lib.db.query",
        lambda sql, params=(): [{"status": "pending"}])

    def fake_transaction(fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 0  # simulate concurrent modification
        mock_conn.cursor.return_value = mock_cursor
        return fn(mock_conn)

    monkeypatch.setattr("app.lib.db.run_in_transaction", fake_transaction)

    r = client.put("/api/workflow/10",
                   json={"status": "reviewing", "user_id": "analyst-1"},
                   headers=HEADERS)
    assert r.status_code == 409
    assert "Concurrent" in r.json()["detail"]


def test_workflow_archived_terminal_returns_422(client, monkeypatch):
    """Attempting to transition out of archived (terminal) state returns 422."""
    monkeypatch.setattr("app.lib.db.query",
        lambda sql, params=(): [{"status": "archived"}])
    r = client.put("/api/workflow/10",
                   json={"status": "reviewing", "user_id": "analyst-1"},
                   headers=HEADERS)
    assert r.status_code == 422
    assert "archived" in r.json()["detail"]


def test_workflow_sample_not_found(client, monkeypatch):
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [])
    r = client.put("/api/workflow/999",
                   json={"status": "reviewing", "user_id": "analyst-1"},
                   headers=HEADERS)
    assert r.status_code == 404


# ─── M_pre4: DELETE /api/patients/{id} ───────────────────────────────────────

def test_delete_patient_returns_204(client, monkeypatch):
    """DELETE /api/patients/{id} returns 204 and executes full cascade."""
    executed_sqls: list[str] = []

    def fake_transaction(fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)  # patient exists
        mock_cursor.execute.side_effect = lambda sql, p=(): executed_sqls.append(sql)
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        return fn(mock_conn)

    monkeypatch.setattr("app.lib.db.run_in_transaction", fake_transaction)
    r = client.delete("/api/patients/1", headers=HEADERS)
    assert r.status_code == 204
    assert any("DELETE FROM variants" in s for s in executed_sqls)
    assert any("DELETE FROM workflow" in s for s in executed_sqls)
    assert any("DELETE FROM samples" in s for s in executed_sqls)
    assert any("DELETE FROM patients" in s for s in executed_sqls)
    assert any("audit_log" in s for s in executed_sqls), "Expected audit log entry for patient delete"
    # Audit must precede the final DELETE FROM patients
    audit_idx = next(i for i, s in enumerate(executed_sqls) if "audit_log" in s)
    patient_idx = next(i for i, s in enumerate(executed_sqls) if "DELETE FROM patients" in s)
    assert audit_idx < patient_idx, "Audit INSERT must precede DELETE FROM patients"


def test_delete_patient_not_found_returns_404(client, monkeypatch):
    """DELETE /api/patients/{id} returns 404 when patient does not exist."""
    def fake_transaction(fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # patient not found
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        return fn(mock_conn)

    monkeypatch.setattr("app.lib.db.run_in_transaction", fake_transaction)
    r = client.delete("/api/patients/999", headers=HEADERS)
    assert r.status_code == 404


# ─── M_pre5: DELETE /api/samples/{id} ────────────────────────────────────────

def test_delete_sample_returns_204(client, monkeypatch):
    """DELETE /api/samples/{id} returns 204 and executes full cascade."""
    executed_sqls: list[str] = []

    def fake_transaction(fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (5,)  # sample exists
        mock_cursor.execute.side_effect = lambda sql, p=(): executed_sqls.append(sql)
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        return fn(mock_conn)

    monkeypatch.setattr("app.lib.db.run_in_transaction", fake_transaction)
    r = client.delete("/api/samples/5", headers=HEADERS)
    assert r.status_code == 204
    assert any("DELETE FROM variants" in s for s in executed_sqls)
    assert any("DELETE FROM workflow" in s for s in executed_sqls)
    assert any("DELETE FROM samples" in s for s in executed_sqls)
    assert any("audit_log" in s for s in executed_sqls), "Expected audit log entry for sample delete"
    # Audit must precede DELETE FROM samples so sample_id is still valid
    audit_idx = next(i for i, s in enumerate(executed_sqls) if "audit_log" in s)
    sample_idx = next(i for i, s in enumerate(executed_sqls) if "DELETE FROM samples" in s)
    assert audit_idx < sample_idx, "Audit INSERT must precede DELETE FROM samples"


def test_delete_sample_not_found_returns_404(client, monkeypatch):
    """DELETE /api/samples/{id} returns 404 when sample does not exist."""
    def fake_transaction(fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # sample not found
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        return fn(mock_conn)

    monkeypatch.setattr("app.lib.db.run_in_transaction", fake_transaction)
    r = client.delete("/api/samples/999", headers=HEADERS)
    assert r.status_code == 404


# ─── M_pre6: locked_by nullable in classification ─────────────────────────────

def test_classification_draft_save_locked_by_null(client, monkeypatch):
    """PUT classification with locked_by=null is a draft save: locked_at must be NULL in SQL."""
    monkeypatch.setattr("app.lib.db.query",
        lambda sql, params=(): [{
            "id": 1, "chrom": "17", "pos": 43094077, "ref": "A", "alt": "T",
            "gene": "BRCA1", "consequence": "missense_variant",
            "hgvs_c": None, "hgvs_p": None, "gnomad_af": None,
            "revel_score": None, "spliceai_max": None, "clinvar_sig": None,
            "info_json": {}, "case_type": "germline",
        }])

    executed_sqls: list[str] = []

    def fake_transaction(fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (42,)
        mock_cursor.execute.side_effect = lambda sql, p=(): executed_sqls.append(sql)
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        return fn(mock_conn)

    monkeypatch.setattr("app.lib.db.run_in_transaction", fake_transaction)

    payload = {
        "framework": "acgs_snv",
        "user_id": "analyst-1",
        "locked_by": None,
        "criteria": [],
    }
    r = client.put("/api/variants/1/classification", json=payload, headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert "classification_id" in body
    # Verify the INSERT uses NULL (not NOW()) for locked_at on a draft save
    insert_sql = next(
        (s for s in executed_sqls if "INSERT INTO variant_classification" in s), None
    )
    assert insert_sql is not None, "Expected INSERT INTO variant_classification"
    assert "NULL" in insert_sql, "Draft save must embed NULL for locked_at"
    assert "NOW()" not in insert_sql, "Draft save must not embed NOW() for locked_at"


def test_classification_locked_by_empty_string_rejected(client):
    """locked_by='' is rejected with 422 at the Pydantic layer — not treated as draft."""
    r = client.put("/api/variants/1/classification",
                   json={"framework": "acgs_snv", "user_id": "analyst-1",
                         "locked_by": "", "criteria": []},
                   headers=HEADERS)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert any("locked_by" in str(d) for d in detail)
