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
        if "COUNT(*) AS n" in sql and "GROUP BY" not in sql else [])
    r = client.get("/api/patients", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_patients_list_returns_items(client, monkeypatch):
    _patient_row = {
        "id": 1, "lab_number": "LAB-001", "name": "Jane Smith",
        "sample_count": 1, "latest_sample_id": 10, "latest_sample_name": "S1",
        "latest_workflow_status": "pending", "latest_ingested_at": None,
        "pipeline_key": "dragen_germline",
    }

    def mock_query(sql, params=()):
        if "COUNT(*) AS n" in sql and "GROUP BY" not in sql:
            return [{"n": 2}]
        return [_patient_row, {**_patient_row, "id": 2, "lab_number": "LAB-002"}]

    monkeypatch.setattr("app.lib.db.query", mock_query)
    r = client.get("/api/patients", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    assert body["total"] == 2
    assert body["items"][0]["lab_number"] == "LAB-001"
    assert body["items"][0]["sample_count"] == 1


def test_patients_list_pagination_params(client, monkeypatch):
    captured = {}
    _row = {
        "id": 1, "lab_number": "LAB-001", "name": None,
        "sample_count": 0, "latest_sample_id": None, "latest_sample_name": None,
        "latest_workflow_status": None, "latest_ingested_at": None, "pipeline_key": None,
    }

    def mock_query(sql, params=()):
        if "COUNT(*) AS n" in sql and "GROUP BY" not in sql:
            return [{"n": 100}]
        captured["params"] = params
        return []

    monkeypatch.setattr("app.lib.db.query", mock_query)
    client.get("/api/patients?limit=10&offset=20", headers=HEADERS)
    assert 10 in captured["params"] and 20 in captured["params"]


def test_patients_list_limit_max_200(client, monkeypatch):
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [{"n": 0}]
        if "COUNT(*) AS n" in sql and "GROUP BY" not in sql else [])
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
                    "id": 10, "name": "26041S0057", "vcf_filename": None, "case_type": "germline",
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

def test_sample_variants_not_found(client, monkeypatch):
    """Unknown sample_id must return 404, not a silent empty list."""
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [])
    r = client.get("/api/samples/999/variants", headers=HEADERS)
    assert r.status_code == 404


def test_sample_variants_returns_list(client, monkeypatch):
    def mock_query(sql, params=()):
        if "SELECT 1 FROM samples" in sql:
            return [{"exists": 1}]
        if "COUNT(*) AS n" in sql:
            return [{"n": 1}]
        return [{
            "id": 100, "chrom": "1", "pos": 12345, "ref": "A", "alt": "G",
            "gene": "BRCA1", "consequence": "missense_variant",
            "hgvs_c": None, "hgvs_p": None, "clinvar_sig": None,
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
    assert body["case_type"] == "germline"
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


# ─── M_pre1: extended PatientSummary fields ───────────────────────────────────

def test_patients_list_includes_pre1_fields(client, monkeypatch):
    """PatientSummary includes sample_count and latest_* aggregate fields (dob removed by migration 004)."""
    _row = {
        "id": 1, "lab_number": "LAB-001", "name": None,
        "sample_count": 3, "latest_sample_id": 10, "latest_sample_name": "SP-001",
        "latest_workflow_status": "reviewing", "latest_ingested_at": "2026-04-01T00:00:00",
        "pipeline_key": "dragen_germline",
    }

    def mock_query(sql, params=()):
        if "COUNT(*) AS n" in sql and "GROUP BY" not in sql:
            return [{"n": 1}]
        return [_row]

    monkeypatch.setattr("app.lib.db.query", mock_query)
    r = client.get("/api/patients", headers=HEADERS)
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert "dob" not in item, "dob was removed by migration 004"
    assert item["sample_count"] == 3
    assert item["latest_sample_name"] == "SP-001"
    assert item["latest_workflow_status"] == "reviewing"
    assert item["pipeline_key"] == "dragen_germline"


# ─── M_pre2: variant filter params ───────────────────────────────────────────

def test_sample_variants_gnomad_af_max_filter(client, monkeypatch):
    """gnomad_af_max query param is accepted and forwarded to DB."""
    captured = {}

    def mock_query(sql, params=()):
        if "SELECT 1 FROM samples" in sql:
            return [{"exists": True}]
        if "COUNT(*) AS n" in sql:
            return [{"n": 0}]
        captured["sql"] = sql
        captured["params"] = params
        return []

    monkeypatch.setattr("app.lib.db.query", mock_query)
    r = client.get("/api/samples/10/variants?gnomad_af_max=0.01", headers=HEADERS)
    assert r.status_code == 200
    assert "gnomad_af" in captured.get("sql", "")


def test_sample_variants_gene_filter(client, monkeypatch):
    """gene query param is accepted."""
    captured = {}

    def mock_query(sql, params=()):
        if "SELECT 1 FROM samples" in sql:
            return [{"exists": True}]
        if "COUNT(*) AS n" in sql:
            return [{"n": 0}]
        captured["params"] = params
        return []

    monkeypatch.setattr("app.lib.db.query", mock_query)
    client.get("/api/samples/10/variants?gene=BRCA1", headers=HEADERS)
    assert "BRCA1" in captured.get("params", ())


def test_sample_variants_sort_by_gene(client, monkeypatch):
    """sort_by=gene and sort_dir=desc are accepted."""
    def mock_query(sql, params=()):
        if "SELECT 1 FROM samples" in sql:
            return [{"exists": True}]
        if "COUNT(*) AS n" in sql:
            return [{"n": 0}]
        return []

    monkeypatch.setattr("app.lib.db.query", mock_query)
    r = client.get("/api/samples/10/variants?sort_by=gene&sort_dir=desc", headers=HEADERS)
    assert r.status_code == 200


def test_sample_variants_invalid_sort_by_rejected(client, monkeypatch):
    """sort_by with unknown column returns 422."""
    monkeypatch.setattr("app.lib.db.query", lambda sql, params=(): [{"n": 0}])
    r = client.get("/api/samples/10/variants?sort_by=evil_column", headers=HEADERS)
    assert r.status_code == 422


# ─── M_pre3: VariantSummary new fields ───────────────────────────────────────

def test_sample_variants_includes_hgvs_and_clinvar(client, monkeypatch):
    """VariantSummary includes hgvs_c, hgvs_p, clinvar_sig (M_pre3)."""
    def mock_query(sql, params=()):
        if "SELECT 1 FROM samples" in sql:
            return [{"exists": 1}]
        if "COUNT(*) AS n" in sql:
            return [{"n": 1}]
        return [{
            "id": 1, "chrom": "17", "pos": 43094077, "ref": "A", "alt": "T",
            "gene": "BRCA1", "consequence": "missense_variant",
            "hgvs_c": "c.5096G>A", "hgvs_p": "p.Arg1699Gln", "clinvar_sig": "Likely_pathogenic",
            "gnomad_af": None, "revel_score": None, "spliceai_max": None,
            "classification": None, "score": None, "framework": None, "locked_at": None,
        }]

    monkeypatch.setattr("app.lib.db.query", mock_query)
    r = client.get("/api/samples/10/variants", headers=HEADERS)
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["hgvs_c"] == "c.5096G>A"
    assert item["hgvs_p"] == "p.Arg1699Gln"
    assert item["clinvar_sig"] == "Likely_pathogenic"


# ─── M_pre7: vcf_filename in SampleSummary ───────────────────────────────────

def test_patient_detail_samples_include_vcf_filename(client, monkeypatch):
    """SampleSummary includes vcf_filename in patient detail response (M_pre7)."""
    def mock_query(sql, params=()):
        if "FROM patients" in sql:
            return [{"id": 1, "lab_number": "LAB-001", "name": None, "created_at": None}]
        return [{
            "id": 10, "name": "SP-001", "vcf_filename": "sample.vcf.gz",
            "case_type": "germline", "pipeline_key": "dragen_germline",
            "ingested_at": None, "workflow_status": "pending",
        }]

    monkeypatch.setattr("app.lib.db.query", mock_query)
    r = client.get("/api/patients/1", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["samples"][0]["vcf_filename"] == "sample.vcf.gz"


def test_sample_variants_consequences_filter(client, monkeypatch):
    """consequences query param builds ANY(%s) WHERE clause."""
    captured = {}

    def mock_query(sql, params=()):
        if "SELECT 1 FROM samples" in sql:
            return [{"exists": 1}]
        if "COUNT(*) AS n" in sql:
            return [{"n": 0}]
        captured["sql"] = sql
        captured["params"] = params
        return []

    monkeypatch.setattr("app.lib.db.query", mock_query)
    client.get(
        "/api/samples/10/variants?consequences=stop_gained,missense_variant",
        headers=HEADERS,
    )
    assert "ANY" in captured.get("sql", "")
    params = list(captured.get("params", ()))
    assert ["stop_gained", "missense_variant"] in params


def test_sample_variants_empty_consequences_ignored(client, monkeypatch):
    """Empty consequences= string is silently ignored — no ANY clause emitted."""
    captured = {}

    def mock_query(sql, params=()):
        if "SELECT 1 FROM samples" in sql:
            return [{"exists": 1}]
        if "COUNT(*) AS n" in sql:
            return [{"n": 0}]
        captured["sql"] = sql
        return []

    monkeypatch.setattr("app.lib.db.query", mock_query)
    client.get("/api/samples/10/variants?consequences=", headers=HEADERS)
    assert "ANY" not in captured.get("sql", "")


def test_sample_variants_sort_by_gene_sql(client, monkeypatch):
    """sort_by=gene&sort_dir=desc produces ORDER BY v.gene DESC in SQL."""
    captured = {}

    def mock_query(sql, params=()):
        if "SELECT 1 FROM samples" in sql:
            return [{"exists": 1}]
        if "COUNT(*) AS n" in sql:
            return [{"n": 0}]
        captured["sql"] = sql
        return []

    monkeypatch.setattr("app.lib.db.query", mock_query)
    client.get("/api/samples/10/variants?sort_by=gene&sort_dir=desc", headers=HEADERS)
    sql = captured.get("sql", "")
    assert "v.gene" in sql
    assert "DESC" in sql


def test_patients_list_search_passes_wildcard_params(client, monkeypatch):
    """?search= forwards ILIKE wildcard params to both COUNT and rows queries."""
    count_params: tuple = ()
    rows_params: tuple = ()

    def mock_query(sql, params=()):
        nonlocal count_params, rows_params
        if "COUNT(*) AS n" in sql and "GROUP BY" not in sql:
            count_params = params
            return [{"n": 1}]
        rows_params = params
        return []

    monkeypatch.setattr("app.lib.db.query", mock_query)
    client.get("/api/patients?search=LAB-001", headers=HEADERS)
    assert "%LAB-001%" in count_params
    assert "%LAB-001%" in rows_params
