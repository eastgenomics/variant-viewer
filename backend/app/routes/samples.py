"""Sample detail and sample variant list endpoints."""
from __future__ import annotations

import asyncio
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.lib import db
from app.middleware.auth import require_api_key
from app.routes.patients import PatientSummary

router = APIRouter(prefix="/api/samples", dependencies=[Depends(require_api_key)])


class SampleDetailResponse(BaseModel):
    id: int
    name: str
    s3_key: str
    case_type: str
    pipeline_key: str | None
    tissue: str | None
    sequencing_date: date | None
    ingested_at: datetime | None
    patient: PatientSummary
    workflow_status: str
    variant_count: int


class VariantSummary(BaseModel):
    id: int
    chrom: str
    pos: int
    ref: str
    alt: str
    gene: str | None
    consequence: str | None
    gnomad_af: float | None
    revel_score: float | None
    spliceai_max: float | None
    classification: str | None
    score: int | None
    framework: str | None
    locked_at: datetime | None


class VariantListResponse(BaseModel):
    items: list[VariantSummary]
    total: int
    limit: int
    offset: int


@router.get("/{sample_id}", response_model=SampleDetailResponse)
async def get_sample(sample_id: int):
    """Return sample detail with patient info, workflow status, and variant count."""
    rows = await asyncio.to_thread(
        db.query,
        """
        SELECT s.id, s.name, s.s3_key, s.case_type, s.pipeline_key,
               s.tissue, s.sequencing_date, s.ingested_at,
               p.id AS patient_id, p.lab_number, p.name AS patient_name,
               COALESCE(w.status, 'pending') AS workflow_status,
               COUNT(v.id) AS variant_count
        FROM samples s
        JOIN patients p ON p.id = s.patient_id
        LEFT JOIN workflow w ON w.sample_id = s.id
        LEFT JOIN variants v ON v.sample_id = s.id
        WHERE s.id = %s
        GROUP BY s.id, p.id, w.status
        """,
        (sample_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Sample not found")

    row = rows[0]
    patient = PatientSummary(
        id=row["patient_id"],
        lab_number=row["lab_number"],
        name=row["patient_name"],
    )
    return SampleDetailResponse(
        id=row["id"],
        name=row["name"],
        s3_key=row["s3_key"],
        case_type=row["case_type"],
        pipeline_key=row["pipeline_key"],
        tissue=row["tissue"],
        sequencing_date=row["sequencing_date"],
        ingested_at=row["ingested_at"],
        patient=patient,
        workflow_status=row["workflow_status"],
        variant_count=row["variant_count"],
    )


@router.get("/{sample_id}/variants", response_model=VariantListResponse)
async def list_sample_variants(
    sample_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Return a paginated list of variants for a sample with classification summary."""
    total_rows = await asyncio.to_thread(
        db.query,
        "SELECT COUNT(*) AS n FROM variants WHERE sample_id = %s",
        (sample_id,),
    )
    total = total_rows[0]["n"]

    rows = await asyncio.to_thread(
        db.query,
        """
        SELECT v.id, v.chrom, v.pos, v.ref, v.alt, v.gene, v.consequence,
               v.gnomad_af, v.revel_score, v.spliceai_max,
               vc.classification, vc.score, vc.framework, vc.locked_at
        FROM variants v
        LEFT JOIN variant_classification vc
               ON vc.variant_id = v.id AND vc.deleted_at IS NULL
        WHERE v.sample_id = %s
        ORDER BY v.chrom, v.pos
        LIMIT %s OFFSET %s
        """,
        (sample_id, limit, offset),
    )
    return VariantListResponse(
        items=[VariantSummary(**r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
