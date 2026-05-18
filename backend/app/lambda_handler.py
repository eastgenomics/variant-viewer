"""AWS Lambda entry point for S3-triggered VCF ingest.

Triggered by ``s3:ObjectCreated`` events on the VCF upload bucket.
Derives the companion manifest S3 key from the VCF key, downloads
both files, validates the manifest, and persists the VCF data via
``ingest_sample()``.

HTTP-style status codes are used in the return value so that
infrastructure-level monitoring can distinguish success (200) from
expected errors (400 / 409) without inspecting log output.
"""

from __future__ import annotations

import logging
import re
import urllib.parse

import boto3
import jsonschema

from app.lib.db import with_transaction
from app.lib.ingest import DuplicateSubmissionError, ingest_sample

logger = logging.getLogger(__name__)


def handler(event: dict, context: object) -> dict:
    """Handle an S3 ObjectCreated event and ingest the uploaded VCF.

    Derives the manifest S3 key by replacing the ``.vcf`` / ``.vcf.gz``
    suffix of the VCF key with ``.manifest.json``.  The entire ingest
    pipeline runs inside a single database transaction.

    Args:
        event: Lambda event payload.  Must contain exactly one S3 record
            in ``event["Records"]``; raises ``RuntimeError`` otherwise to
            trigger Lambda retry / DLQ handling.
        context: Lambda runtime context (unused).

    Returns:
        A dict with ``statusCode`` and either ``sample_id`` (success) or
        ``error`` (failure)::

            {"statusCode": 200, "sample_id": <int>}   # success
            {"statusCode": 409, "error": <str>}        # duplicate VCF
            {"statusCode": 400, "error": <str>}        # bad manifest / key

    Raises:
        RuntimeError: If the event contains a number of S3 records other
            than exactly one (triggers Lambda retry).
        Any exception not caught by the inner ``try`` block propagates to
        Lambda, which retries the invocation according to its retry policy.
    """
    records = event.get("Records", [])
    if len(records) != 1:
        raise RuntimeError(f"Expected exactly 1 S3 record, got {len(records)}")
    record    = records[0]["s3"]
    bucket    = record["bucket"]["name"]
    # S3 event keys are URL-encoded (spaces as '+', special chars percent-encoded).
    # unquote_plus must be used — plain unquote does not decode '+' as a space.
    vcf_key   = urllib.parse.unquote_plus(record["object"]["key"])
    manifest_key = re.sub(r"\.vcf(\.gz)?$", ".manifest.json", vcf_key)

    logger.info("ingest triggered: bucket=%s key=%s", bucket, vcf_key)

    s3 = boto3.client("s3")  # boto3 reads AWS_REGION from the Lambda runtime environment
    try:
        with with_transaction() as conn:
            sample_id = ingest_sample(vcf_key, manifest_key, bucket, s3, conn)
        logger.info("ingest complete: sample_id=%d", sample_id)
        return {"statusCode": 200, "sample_id": sample_id}

    except DuplicateSubmissionError as exc:
        logger.warning("duplicate submission: %s", exc)
        return {"statusCode": 409, "error": str(exc)}

    except (ValueError, jsonschema.ValidationError) as exc:
        logger.error("invalid submission: %s", exc)
        return {"statusCode": 400, "error": str(exc)}
    # All other exceptions propagate — Lambda will retry.
