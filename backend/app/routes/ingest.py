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

_VCF_RE = re.compile(r"\.vcf(\.gz)?$")

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])


class IngestRequest(BaseModel):
    vcf_s3_key: str
    user_id: str


def _manifest_key(vcf_key: str) -> str:
    return _VCF_RE.sub(".manifest.json", vcf_key)


@router.post("/ingest")
async def manual_ingest(body: IngestRequest) -> dict:
    """Trigger an ingest for a VCF already uploaded to S3."""
    bucket = os.environ.get("VCF_BUCKET_NAME")
    if not bucket:
        raise HTTPException(status_code=500, detail="VCF_BUCKET_NAME not configured")
    region = os.environ.get("AWS_REGION", "eu-west-2")
    s3 = boto3.client("s3", region_name=region)

    manifest_key = _manifest_key(body.vcf_s3_key)

    def _do(conn):
        sample_id = ingest_sample(body.vcf_s3_key, manifest_key, bucket, s3, conn)
        # Record who triggered the ingest in the audit log.
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO audit_log "
                "(user_id, action, entity_type, entity_id, old_value, new_value) "
                "VALUES (%s, 'ingest', 'sample', %s, NULL, NULL)",
                (body.user_id, sample_id),
            )
        return sample_id

    try:
        sample_id = await asyncio.to_thread(db.run_in_transaction, _do)
        return {"sample_id": sample_id}
    except DuplicateSubmissionError as exc:
        raise HTTPException(status_code=409, detail=f"Duplicate submission: {exc}") from exc
    except psycopg2.errors.UniqueViolation as exc:
        # TOCTOU race: two concurrent ingests of the same key both pass
        # check_idempotency() then one loses the UNIQUE constraint INSERT.
        raise HTTPException(
            status_code=409,
            detail="Duplicate submission: concurrent ingest detected",
        ) from exc
    except ValueError as exc:
        # Covers unsupported file extensions / bad manifest structure.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
