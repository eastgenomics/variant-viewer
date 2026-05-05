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
