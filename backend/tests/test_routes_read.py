"""Tests for PR 6 read-only API routes."""
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
    assert r.status_code == 422  # FastAPI validation: limit ≤ 200


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
                {
                    "id": 10, "name": "26041S0057", "case_type": "germline",
                    "pipeline_key": "dragen_germline", "ingested_at": None,
                    "workflow_status": "pending",
                },
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
        if call_count["n"] == 1:  # variant + case_type
            return [{"id": 100, "chrom": "1", "pos": 12345, "ref": "A", "alt": "G",
                     "gene": "BRCA1", "consequence": "missense_variant",
                     "hgvs_c": "c.100A>G", "hgvs_p": "p.Thr34Ala",
                     "gnomad_af": 0.0001, "revel_score": 0.75, "spliceai_max": 0.1,
                     "clinvar_sig": None, "info_json": {}, "case_type": "germline"}]
        if call_count["n"] == 2:  # active classification
            return [{"id": 50, "framework": "acgs_snv", "framework_version": "ACGS 2024",
                     "score": None, "classification": None,
                     "locked_at": None, "locked_by": None}]
        if call_count["n"] == 3:  # criteria
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
        return []  # no active classification

    monkeypatch.setattr("app.lib.db.query", mock_query)
    r = client.get("/api/variants/100", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["active_classification"] is None


# ─── Config criteria ──────────────────────────────────────────────────────────

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
