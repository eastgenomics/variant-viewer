"""PR 7 — Presigned S3 upload URL generation.

POST /api/upload-url  →  returns signed PUT URLs for VCF + manifest files.
"""
import os
import re
from datetime import datetime

import boto3
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.auth import require_api_key

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])

_VCF_RE = re.compile(r"\.vcf(\.gz)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_EXPIRES = 3600


class UploadUrlRequest(BaseModel):
    vcf_filename: str
    run_date: str | None = None


class UploadUrlResponse(BaseModel):
    vcf_url: str
    manifest_url: str
    vcf_key: str
    manifest_key: str
    expires_in: int


@router.post("/upload-url", response_model=UploadUrlResponse)
async def get_upload_url(body: UploadUrlRequest) -> UploadUrlResponse:
    """Return presigned PUT URLs for a VCF and its companion manifest file."""
    if not _VCF_RE.search(body.vcf_filename):
        raise HTTPException(
            status_code=400,
            detail=f"vcf_filename must end with .vcf or .vcf.gz: {body.vcf_filename!r}",
        )

    # Reject filenames that could escape the runs/{date}/ key prefix.
    safe_filename = body.vcf_filename
    if "/" in safe_filename or ".." in safe_filename:
        raise HTTPException(
            status_code=400,
            detail="vcf_filename must not contain '/' or '..'",
        )

    bucket = os.environ.get("VCF_BUCKET_NAME")
    if not bucket:
        raise HTTPException(status_code=500, detail="VCF_BUCKET_NAME not configured")

    if body.run_date is not None and not _DATE_RE.match(body.run_date):
        raise HTTPException(
            status_code=400,
            detail=f"run_date must be YYYY-MM-DD, got {body.run_date!r}",
        )
    date_prefix = body.run_date or datetime.today().strftime("%Y-%m-%d")
    vcf_key = f"runs/{date_prefix}/{safe_filename}"
    manifest_key = _VCF_RE.sub(".manifest.json", vcf_key)

    region = os.environ.get("AWS_REGION", "eu-west-2")
    s3 = boto3.client("s3", region_name=region)

    vcf_url = s3.generate_presigned_url(
        "put_object", Params={"Bucket": bucket, "Key": vcf_key}, ExpiresIn=_EXPIRES
    )
    manifest_url = s3.generate_presigned_url(
        "put_object", Params={"Bucket": bucket, "Key": manifest_key}, ExpiresIn=_EXPIRES
    )

    return UploadUrlResponse(
        vcf_url=vcf_url,
        manifest_url=manifest_url,
        vcf_key=vcf_key,
        manifest_key=manifest_key,
        expires_in=_EXPIRES,
    )
