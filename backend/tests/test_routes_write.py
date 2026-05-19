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
    assert audit[1][0] == "analyst-1"  # user_id
    assert audit[1][1] == 42           # entity_id (sample_id)


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
    assert audit[1][0] == "analyst-1"                                    # user_id
    assert audit[1][3] == 10                                             # entity_id (sample_id)
    assert json.loads(audit[1][4]) == {"status": "pending"}             # old_value
    assert json.loads(audit[1][5]) == {"status": "reviewing"}           # new_value


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
