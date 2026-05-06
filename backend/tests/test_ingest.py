import pytest
from unittest.mock import MagicMock, patch, call

from app.lib.ingest import (
    DuplicateSubmissionError,
    check_idempotency,
)


def _make_conn(fetchone_side_effect):
    """Build a mock psycopg2 connection whose cursor.fetchone() returns
    successive values from *fetchone_side_effect*."""
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone.side_effect = fetchone_side_effect
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor


# ---------------------------------------------------------------------------
# Exact duplicate — same s3_key already in samples table
# ---------------------------------------------------------------------------

def test_exact_duplicate_raises():
    """An s3_key that already exists must raise DuplicateSubmissionError."""
    conn, cursor = _make_conn([(42,)])   # fetchone returns existing sample row
    with pytest.raises(DuplicateSubmissionError) as exc_info:
        check_idempotency(
            s3_key="path/to/sample.vcf.gz",
            lab_number="LAB-001",
            sample_name="26041S0057",
            conn=conn,
        )
    err = exc_info.value
    assert err.duplicate_type == "exact"
    assert err.existing_sample_id == 42


def test_exact_duplicate_message_contains_s3_key():
    conn, _ = _make_conn([(7,)])
    with pytest.raises(DuplicateSubmissionError) as exc_info:
        check_idempotency("bucket/run/case.vcf.gz", "LAB-X", "SAMP1", conn)
    assert "bucket/run/case.vcf.gz" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Near-duplicate — same lab_number + sample_name, different s3_key
# ---------------------------------------------------------------------------

def test_near_duplicate_raises():
    """Same patient+sample already ingested under a different VCF must raise."""
    # First fetchone (exact check) returns None; second (near check) hits.
    conn, cursor = _make_conn([None, (99, "old/path.vcf.gz")])
    with pytest.raises(DuplicateSubmissionError) as exc_info:
        check_idempotency(
            s3_key="new/path.vcf.gz",
            lab_number="LAB-001",
            sample_name="26041S0057",
            conn=conn,
        )
    err = exc_info.value
    assert err.duplicate_type == "near"
    assert err.existing_sample_id == 99


def test_near_duplicate_message_contains_lab_number_and_sample():
    conn, _ = _make_conn([None, (5, "old.vcf.gz")])
    with pytest.raises(DuplicateSubmissionError) as exc_info:
        check_idempotency("new.vcf.gz", "LAB-999", "MYSAMPLE", conn)
    msg = str(exc_info.value)
    assert "LAB-999" in msg
    assert "MYSAMPLE" in msg


# ---------------------------------------------------------------------------
# Clean path — no existing record
# ---------------------------------------------------------------------------

def test_clean_submission_does_not_raise():
    """A genuinely new submission must pass without raising."""
    conn, _ = _make_conn([None, None])   # neither query finds a match
    check_idempotency("fresh/upload.vcf.gz", "LAB-002", "NEW_SAMPLE", conn)


# ---------------------------------------------------------------------------
# Query structure — exact check runs before near check
# ---------------------------------------------------------------------------

def test_exact_check_runs_first():
    """The s3_key query must be executed before the lab_number+sample query."""
    conn, cursor = _make_conn([None, None])
    check_idempotency("s3key", "LAB-1", "SAMP", conn)
    calls = cursor.execute.call_args_list
    # First query must reference s3_key
    first_sql = calls[0][0][0].lower()
    assert "s3_key" in first_sql
    # Second query must reference lab_number and name
    second_sql = calls[1][0][0].lower()
    assert "lab_number" in second_sql
    assert "name" in second_sql


def test_near_check_skipped_when_exact_hits():
    """If the exact duplicate is found, the near-duplicate query must not run."""
    conn, cursor = _make_conn([(1,)])
    with pytest.raises(DuplicateSubmissionError):
        check_idempotency("s3key", "LAB-1", "SAMP", conn)
    # Only one execute call (the exact check)
    assert cursor.execute.call_count == 1


# ===========================================================================
# ingest_sample tests (PR 5)
# ===========================================================================

import json
import jsonschema
from pathlib import Path
from app.lib.vcf_parser import VcfMeta
from app.lib.ingest import ingest_sample

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_VALID_MANIFEST = {
    "resourceType": "Bundle",
    "type": "collection",
    "entry": [
        {"resource": {
            "resourceType": "Patient",
            "identifier": [{"system": "https://fhir.example-lab.org/Id/lab-number",
                             "value": "LAB-001"}],
            "birthDate": "1980-01-01",
        }},
        {"resource": {
            "resourceType": "Specimen",
            "identifier": [{"value": "26041S0057"}],
            "extension": [{"url": "https://example.org/fhir/StructureDefinition/case-type",
                            "valueCode": "germline"}],
        }},
        {"resource": {
            "resourceType": "Task",
            "status": "completed",
            "code": {"text": "dragen_germline"},
        }},
    ],
}

_VCF_KEY      = "runs/2024/26041S0057.vcf.gz"
_MANIFEST_KEY = "runs/2024/26041S0057.manifest.json"
_BUCKET       = "variant-viewer-vcf-749929395031"


def _make_s3_mock(manifest=None):
    manifest_content = json.dumps(manifest or _VALID_MANIFEST)

    def download_side_effect(bucket, key, dest):
        if key.endswith(".manifest.json"):
            Path(dest).write_text(manifest_content)
        else:
            Path(dest).write_text("##fileformat=VCFv4.2\n")

    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = download_side_effect
    return mock_s3


def _make_db_mock(patient_id=1, sample_id=2):
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)
    # check_idempotency calls fetchone twice (exact, near) before the INSERT RETURNINGs
    mock_cursor.fetchone.side_effect = [None, None, (patient_id,), (sample_id,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor


# ---------------------------------------------------------------------------
# Happy path — no variants
# ---------------------------------------------------------------------------

@patch("app.lib.ingest.parse_vcf")
def test_ingest_returns_sample_id(mock_parse_vcf):
    mock_parse_vcf.return_value = VcfMeta(pipeline_key="dragen_germline", header_lines=[])
    conn, _ = _make_db_mock(sample_id=42)
    s3 = _make_s3_mock()

    result = ingest_sample(_VCF_KEY, _MANIFEST_KEY, _BUCKET, s3, conn)

    assert result == 42
    assert s3.download_file.call_count == 2


@patch("app.lib.ingest.parse_vcf")
def test_ingest_s3_downloads_both_files(mock_parse_vcf):
    mock_parse_vcf.return_value = VcfMeta(pipeline_key=None, header_lines=[])
    conn, _ = _make_db_mock()
    s3 = _make_s3_mock()

    ingest_sample(_VCF_KEY, _MANIFEST_KEY, _BUCKET, s3, conn)

    assert s3.download_file.call_count == 2
    keys_downloaded = {c[0][1] for c in s3.download_file.call_args_list}
    assert _VCF_KEY in keys_downloaded
    assert _MANIFEST_KEY in keys_downloaded


@patch("app.lib.ingest.parse_vcf")
def test_ingest_sql_rows_inserted(mock_parse_vcf):
    mock_parse_vcf.return_value = VcfMeta(pipeline_key="dragen_germline", header_lines=[])
    conn, cursor = _make_db_mock()

    ingest_sample(_VCF_KEY, _MANIFEST_KEY, _BUCKET, _make_s3_mock(), conn)

    sqls = [c[0][0].lower() for c in cursor.execute.call_args_list]
    assert any("insert into patients" in s for s in sqls)
    assert any("insert into samples" in s for s in sqls)
    assert any("insert into workflow" in s for s in sqls)


# ---------------------------------------------------------------------------
# Happy path — with one variant
# ---------------------------------------------------------------------------

@patch("app.lib.ingest.parse_vcf")
def test_ingest_with_variant_inserts_classification_and_criteria(mock_parse_vcf):
    from app.lib.vcf_parser import VcfVariant

    test_variant = VcfVariant(
        chrom="1", pos=100, ref="A", alt="G",
        qual=50.0, filter="PASS",
        gene="BRCA1", consequence="missense_variant",
        hgvs_c="c.100A>G", hgvs_p=None,
        gnomad_af=0.000001, clinvar_sig=None,
        revel_score=0.75, spliceai_max=None,
        info_json={},
    )

    def fake_parse(path, on_variant=None):
        if on_variant:
            on_variant(test_variant)
        return VcfMeta(pipeline_key="dragen_germline", header_lines=[])

    mock_parse_vcf.side_effect = fake_parse

    # fetchone: patient_id, sample_id, variant_id, classification_id
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone.side_effect = [None, None, (1,), (2,), (3,), (4,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    result = ingest_sample(_VCF_KEY, _MANIFEST_KEY, _BUCKET, _make_s3_mock(), mock_conn)

    assert result == 2
    sqls = [c[0][0].lower() for c in mock_cursor.execute.call_args_list]
    assert any("insert into variants" in s for s in sqls)
    assert any("insert into variant_classification" in s for s in sqls)
    assert any("insert into classification_criterion" in s for s in sqls)


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------

def test_ingest_invalid_key_format():
    with pytest.raises(ValueError, match="Unsupported VCF key format"):
        ingest_sample("runs/sample.bam", "runs/sample.manifest.json",
                      _BUCKET, MagicMock(), MagicMock())


def test_ingest_schema_validation_failure():
    bad_manifest = {"resourceType": "Bundle", "type": "collection"}  # missing 'entry'
    with pytest.raises(jsonschema.ValidationError):
        ingest_sample(_VCF_KEY, _MANIFEST_KEY, _BUCKET, _make_s3_mock(bad_manifest), MagicMock())


def test_ingest_manifest_parse_failure():
    # Passes JSON schema but parse_manifest raises ValueError (invalid case_type)
    bad_case_type = {
        "resourceType": "Bundle", "type": "collection",
        "entry": [
            {"resource": {"resourceType": "Patient",
                          "identifier": [{"value": "LAB-001"}]}},
            {"resource": {"resourceType": "Specimen",
                          "identifier": [{"value": "S001"}],
                          "extension": [{"url": "https://example.org/fhir/StructureDefinition/case-type",
                                         "valueCode": "unknown_type"}]}},
            {"resource": {"resourceType": "Task", "status": "completed"}},
        ],
    }
    with pytest.raises(ValueError):
        ingest_sample(_VCF_KEY, _MANIFEST_KEY, _BUCKET, _make_s3_mock(bad_case_type), MagicMock())


# ---------------------------------------------------------------------------
# Duplicate submissions
# ---------------------------------------------------------------------------

@patch("app.lib.ingest.parse_vcf")
def test_ingest_exact_duplicate(mock_parse_vcf):
    mock_parse_vcf.return_value = VcfMeta(pipeline_key=None, header_lines=[])

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone.return_value = (99,)  # exact check finds existing row
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with pytest.raises(DuplicateSubmissionError) as exc_info:
        ingest_sample(_VCF_KEY, _MANIFEST_KEY, _BUCKET, _make_s3_mock(), mock_conn)
    assert exc_info.value.duplicate_type == "exact"


@patch("app.lib.ingest.parse_vcf")
def test_ingest_near_duplicate(mock_parse_vcf):
    mock_parse_vcf.return_value = VcfMeta(pipeline_key=None, header_lines=[])

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone.side_effect = [None, (55, "old/path.vcf.gz")]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with pytest.raises(DuplicateSubmissionError) as exc_info:
        ingest_sample(_VCF_KEY, _MANIFEST_KEY, _BUCKET, _make_s3_mock(), mock_conn)
    assert exc_info.value.duplicate_type == "near"
