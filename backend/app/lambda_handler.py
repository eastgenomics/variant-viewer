from __future__ import annotations

import logging
import re

import boto3
import jsonschema

from app.lib.db import with_transaction
from app.lib.ingest import DuplicateSubmissionError, ingest_sample

logger = logging.getLogger(__name__)


def handler(event: dict, context: object) -> dict:
    """Lambda entry point — triggered by S3 ObjectCreated events."""
    record    = event["Records"][0]["s3"]
    bucket    = record["bucket"]["name"]
    vcf_key   = record["object"]["key"]
    manifest_key = re.sub(r"\.vcf(\.gz)?$", ".manifest.json", vcf_key)

    logger.info("ingest triggered: bucket=%s key=%s", bucket, vcf_key)

    s3 = boto3.client("s3", region_name="eu-west-2")
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
