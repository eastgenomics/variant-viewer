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
# Clean path — no existing record
# ---------------------------------------------------------------------------

def test_clean_submission_does_not_raise():
    """A genuinely new submission must pass without raising."""
    conn, _ = _make_conn([None])
    check_idempotency("fresh/upload.vcf.gz", "LAB-002", "NEW_SAMPLE", conn)


def test_multiple_vcfs_same_specimen_allowed():
    """Different VCFs for the same patient+specimen must not raise —
    multiple panel uploads are a supported workflow (e.g. cardiac panel +
    ID panel from the same specimen)."""
    # Near-duplicate check has been removed; only the s3_key is checked.
    conn, cursor = _make_conn([None])  # exact check finds nothing
    check_idempotency("new/panel_b.vcf.gz", "LAB-001", "26041S0057", conn)
    # Only one query should be executed (the s3_key check)
    assert cursor.execute.call_count == 1


# ---------------------------------------------------------------------------
# Query structure
# ---------------------------------------------------------------------------

def test_only_s3_key_query_executed_on_clean_path():
    """Only the s3_key SELECT is issued; no lab_number+name query."""
    conn, cursor = _make_conn([None])
    check_idempotency("s3key", "LAB-1", "SAMP", conn)
    assert cursor.execute.call_count == 1
    sql = cursor.execute.call_args_list[0][0][0].lower()
    assert "s3_key" in sql
    assert "lab_number" not in sql


def test_exact_duplicate_short_circuits():
    """When the exact duplicate is found exactly one query runs."""
    conn, cursor = _make_conn([(1,)])
    with pytest.raises(DuplicateSubmissionError):
        check_idempotency("s3key", "LAB-1", "SAMP", conn)
    assert cursor.execute.call_count == 1
