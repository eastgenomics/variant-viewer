"""PR 7 — Manual ingest trigger.

POST /api/ingest  →  downloads VCF + manifest from S3, parses, classifies,
                      and writes sample + variants to the DB inside a single
                      transaction.
"""
import asyncio
from datetime import date
import os
import re
import tempfile
from pathlib import Path as _Path
from typing import Literal

import boto3
import psycopg2.errors
import psycopg2.extras
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.lib import db
from app.lib.classification_engine import get_framework_version, select_framework
from app.lib.ingest import DuplicateSubmissionError, ingest_sample
from app.lib.pre_compute_criteria import pre_compute_criteria
from app.lib.vcf_parser import VcfVariant, parse_vcf
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
    if not _VCF_RE.search(body.vcf_s3_key):
        raise HTTPException(
            status_code=400,
            detail=f"vcf_s3_key must end with .vcf or .vcf.gz: {body.vcf_s3_key!r}",
        )

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



@router.post("/ingest-direct", status_code=200)
async def ingest_direct(
    vcf: UploadFile = File(..., description="VCF file (.vcf or .vcf.gz)"),
    lab_number: str = Form(...),
    specimen_name: str = Form(...),
    case_type: Literal["germline", "somatic"] = Form("germline"),
    pipeline_key: str | None = Form(None),
    user_id: str = Form("analyst"),
    sequencing_date: date | None = Form(None),
):
    """
    Dev-only: ingest a VCF uploaded directly as multipart/form-data.
    Parses the VCF locally and writes directly to the DB (no S3 required).
    """
    if not vcf.filename or not _VCF_RE.search(vcf.filename):
        raise HTTPException(status_code=400, detail="File must be a .vcf or .vcf.gz")

    # Guard against oversized uploads before reading into memory
    _MAX_VCF_BYTES = 500 * 1024 * 1024  # 500 MB
    if vcf.size is not None and vcf.size > _MAX_VCF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"VCF file too large ({vcf.size:,} bytes). Maximum is 500 MB.",
        )
    contents = await vcf.read()
    if len(contents) > _MAX_VCF_BYTES:
        raise HTTPException(status_code=413, detail="VCF file too large. Maximum is 500 MB.")
    suffix = ".vcf.gz" if (vcf.filename or "").endswith(".gz") else ".vcf"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(contents)
        tmp.flush()
        vcf_path = _Path(tmp.name)
        variants: list[VcfVariant] = []
        try:
            meta = parse_vcf(vcf_path, on_variant=variants.append)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"VCF parse error: {e}")

    effective_pipeline = pipeline_key or meta.pipeline_key or "dragen_germline"
    # Capture filename before the _do closure (UploadFile.filename may be None after read)
    vcf_name = vcf.filename

    def _do(conn):
        with conn.cursor() as cur:
            # Upsert patient
            cur.execute(
                """INSERT INTO patients (lab_number)
                   VALUES (%s)
                   ON CONFLICT (lab_number) DO UPDATE SET lab_number = EXCLUDED.lab_number
                   RETURNING id""",
                (lab_number,),
            )
            patient_id: int = cur.fetchone()[0]

            # Check idempotency on specimen_name for this patient
            cur.execute(
                "SELECT id FROM samples WHERE patient_id = %s AND name = %s AND s3_key = %s",
                (patient_id, specimen_name, f"direct:{vcf_name}"),
            )
            if cur.fetchone():
                raise DuplicateSubmissionError(
                    f"Duplicate direct upload: {vcf_name!r} already ingested for patient",
                    existing_sample_id=-1,
                    duplicate_type="exact",
                )

            # Insert sample (s3_key = sentinel for direct uploads)
            cur.execute(
                """INSERT INTO samples
                   (patient_id, name, vcf_filename, s3_key, pipeline_key, case_type, sequencing_date)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (patient_id, specimen_name, vcf_name,
                 f"direct:{vcf_name}", effective_pipeline, case_type, sequencing_date),
            )
            sample_id: int = cur.fetchone()[0]

            # Insert variants with classification shell and pre-computed criteria
            # (mirrors the production ingest_sample path in lib/ingest.py)
            for v in variants:
                cur.execute(
                    """INSERT INTO variants
                       (sample_id, chrom, pos, ref, alt, gene, consequence,
                        hgvs_c, hgvs_p, gnomad_af, revel_score, spliceai_max,
                        clinvar_sig, info_json)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING id""",
                    (sample_id, v.chrom, v.pos, v.ref, v.alt, v.gene,
                     v.consequence, v.hgvs_c, v.hgvs_p, v.gnomad_af,
                     v.revel_score, v.spliceai_max, v.clinvar_sig,
                     psycopg2.extras.Json(v.info_json or {})),
                )
                variant_id: int = cur.fetchone()[0]
                # Classification shell
                framework, _ = select_framework(case_type, v.gene)
                framework_version = get_framework_version(framework)
                cur.execute(
                    "INSERT INTO variant_classification "
                    "(variant_id, framework, framework_version) "
                    "VALUES (%s, %s, %s) RETURNING id",
                    (variant_id, framework, framework_version),
                )
                classification_id: int = cur.fetchone()[0]
                # Pre-computed criteria (e.g. BA1 from gnomAD AF)
                for suggestion in pre_compute_criteria(v, case_type):
                    cur.execute(
                        "INSERT INTO classification_criterion "
                        "(classification_id, criterion_code, applied, strength, "
                        "pre_computed, pre_computed_value) "
                        "VALUES (%s, %s, FALSE, %s, TRUE, %s)",
                        (classification_id, suggestion.criterion_code,
                         suggestion.suggested_strength, suggestion.pre_computed_value),
                    )

            # Insert workflow row
            cur.execute(
                "INSERT INTO workflow (sample_id, status) VALUES (%s, 'pending')",
                (sample_id,),
            )

            # Audit log
            cur.execute(
                "INSERT INTO audit_log (user_id, action, entity_type, entity_id, old_value, new_value) "
                "VALUES (%s, 'ingest_direct', 'sample', %s, NULL, NULL)",
                (user_id, sample_id),
            )
            return sample_id

    try:
        sample_id = await asyncio.to_thread(db.run_in_transaction, _do)
    except DuplicateSubmissionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingest failed: {e}")

    return {"sample_id": sample_id, "message": "Ingested successfully"}
