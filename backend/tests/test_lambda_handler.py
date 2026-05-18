"""Tests for app.lambda_handler.

Covers all four handler return paths:
- Wrong S3 record count  → RuntimeError (Lambda retry / DLQ)
- Success                → {"statusCode": 200, "sample_id": <int>}
- DuplicateSubmissionError → {"statusCode": 409, "error": <str>}
- ValueError / ValidationError → {"statusCode": 400, "error": <str>}

Also verifies that URL-encoded S3 event keys are decoded before use.
"""

from __future__ import annotations

import pytest
import jsonschema
from unittest.mock import MagicMock, patch

from app.lambda_handler import handler
from app.lib.ingest import DuplicateSubmissionError


def _event(key: str = "runs/2024/sample.vcf.gz", bucket: str = "vcf-bucket") -> dict:
    """Minimal S3 ObjectCreated event with a single record."""
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": key},
                }
            }
        ]
    }


# ---------------------------------------------------------------------------
# Wrong record count — triggers Lambda retry
# ---------------------------------------------------------------------------

def test_handler_no_records_raises():
    """Zero S3 records must raise RuntimeError to trigger Lambda retry."""
    with pytest.raises(RuntimeError, match="Expected exactly 1"):
        handler({"Records": []}, {})


def test_handler_multiple_records_raises():
    """More than one S3 record must raise RuntimeError to trigger Lambda retry."""
    two_records = [
        {"s3": {"bucket": {"name": "b"}, "object": {"key": "k.vcf.gz"}}}
    ] * 2
    with pytest.raises(RuntimeError, match="Expected exactly 1"):
        handler({"Records": two_records}, {})


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

@patch("app.lambda_handler.boto3.client")
@patch("app.lambda_handler.with_transaction")
@patch("app.lambda_handler.ingest_sample", return_value=42)
def test_handler_success_returns_200(mock_ingest, mock_tx, mock_s3):
    """A clean ingest must return statusCode 200 and the new sample_id."""
    result = handler(_event(), {})
    assert result == {"statusCode": 200, "sample_id": 42}


@patch("app.lambda_handler.boto3.client")
@patch("app.lambda_handler.with_transaction")
@patch("app.lambda_handler.ingest_sample", return_value=7)
def test_handler_success_calls_ingest_with_correct_keys(mock_ingest, mock_tx, mock_s3):
    """ingest_sample must receive the vcf_key and the derived manifest_key."""
    handler(_event(key="runs/2024/sample.vcf.gz"), {})
    args = mock_ingest.call_args[0]
    assert args[0] == "runs/2024/sample.vcf.gz"
    assert args[1] == "runs/2024/sample.manifest.json"


# ---------------------------------------------------------------------------
# Duplicate submission — 409
# ---------------------------------------------------------------------------

@patch("app.lambda_handler.boto3.client")
@patch("app.lambda_handler.with_transaction")
@patch("app.lambda_handler.ingest_sample")
def test_handler_duplicate_returns_409(mock_ingest, mock_tx, mock_s3):
    """DuplicateSubmissionError must be caught and returned as 409."""
    mock_ingest.side_effect = DuplicateSubmissionError(
        "VCF already ingested", existing_sample_id=1, duplicate_type="exact"
    )
    result = handler(_event(), {})
    assert result["statusCode"] == 409
    assert "VCF already ingested" in result["error"]


# ---------------------------------------------------------------------------
# Bad manifest / key — 400
# ---------------------------------------------------------------------------

@patch("app.lambda_handler.boto3.client")
@patch("app.lambda_handler.with_transaction")
@patch("app.lambda_handler.ingest_sample")
def test_handler_value_error_returns_400(mock_ingest, mock_tx, mock_s3):
    """ValueError from ingest_sample must be caught and returned as 400."""
    mock_ingest.side_effect = ValueError("Unsupported VCF key format: 'bad.bam'")
    result = handler(_event(), {})
    assert result["statusCode"] == 400
    assert "Unsupported VCF key format" in result["error"]


@patch("app.lambda_handler.boto3.client")
@patch("app.lambda_handler.with_transaction")
@patch("app.lambda_handler.ingest_sample")
def test_handler_validation_error_returns_400(mock_ingest, mock_tx, mock_s3):
    """jsonschema.ValidationError from ingest_sample must be caught and returned as 400."""
    mock_ingest.side_effect = jsonschema.ValidationError("'entry' is a required property")
    result = handler(_event(), {})
    assert result["statusCode"] == 400
    assert "'entry' is a required property" in result["error"]


# ---------------------------------------------------------------------------
# S3 key URL-decoding (critical AWS gotcha)
# ---------------------------------------------------------------------------

@patch("app.lambda_handler.boto3.client")
@patch("app.lambda_handler.with_transaction")
@patch("app.lambda_handler.ingest_sample", return_value=1)
def test_handler_url_decodes_percent_encoded_key(mock_ingest, mock_tx, mock_s3):
    """Percent-encoded characters in S3 event keys must be decoded."""
    handler(_event(key="runs%2F2024%2Fsample.vcf.gz"), {})
    vcf_key_used = mock_ingest.call_args[0][0]
    assert vcf_key_used == "runs/2024/sample.vcf.gz"


@patch("app.lambda_handler.boto3.client")
@patch("app.lambda_handler.with_transaction")
@patch("app.lambda_handler.ingest_sample", return_value=1)
def test_handler_url_decodes_plus_as_space(mock_ingest, mock_tx, mock_s3):
    """S3 encodes spaces as '+'; unquote_plus must decode them correctly."""
    handler(_event(key="runs/2024/sample+name.vcf.gz"), {})
    vcf_key_used = mock_ingest.call_args[0][0]
    assert vcf_key_used == "runs/2024/sample name.vcf.gz"
