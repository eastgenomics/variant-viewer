"""PR 7 — Manual ingest trigger.

POST /api/ingest  →  downloads VCF + manifest from S3, parses, classifies,
                      and writes sample + variants to the DB inside a single
                      transaction.
"""
import asyncio
import os
import re

import boto3
import psycopg2.errors
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.lib import db
from app.lib.ingest import DuplicateSubmissionError, ingest_sample
from app.middleware.auth import require_api_key

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])

_VCF_RE = re.compile(r"\.vcf(\.gz)?$")


class IngestRequest(BaseModel):
    vcf_s3_key: str
    user_id: str


def _manifest_key(vcf_key: str) -> str:
    return _VCF_RE.sub(".manifest.json", vcf_key)


@router.post("/ingest")
async def manual_ingest(body: IngestRequest) -> dict:
    """Trigger an ingest for a VCF already uploaded to S3."""
    bucket = os.environ.get("VCF_BUCKET_NAME", "")
    region = os.environ.get("AWS_REGION", "eu-west-2")
    s3 = boto3.client("s3", region_name=region)

    manifest_key = _manifest_key(body.vcf_s3_key)

    def _do(conn):
        return ingest_sample(body.vcf_s3_key, manifest_key, bucket, s3, conn)

    try:
        sample_id = await asyncio.to_thread(db.run_in_transaction, _do)
        return {"sample_id": sample_id}
    except DuplicateSubmissionError as exc:
        raise HTTPException(status_code=409, detail=f"Duplicate submission: {exc}")
    except psycopg2.errors.UniqueViolation:
        # TOCTOU race: two concurrent ingests of the same key both pass
        # check_idempotency() then one loses the UNIQUE constraint INSERT.
        raise HTTPException(
            status_code=409,
            detail="Duplicate submission: concurrent ingest detected",
        )
    except (ValueError, Exception) as exc:
        # ValueError covers unsupported file extensions / bad manifest structure;
        # jsonschema.ValidationError inherits from Exception.
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=400, detail=str(exc))
        raise
