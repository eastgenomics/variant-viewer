"""Patient list and detail endpoints."""
from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.lib import db
from app.middleware.auth import require_api_key

router = APIRouter(prefix="/api/patients", dependencies=[Depends(require_api_key)])


class PatientSummary(BaseModel):
    id: int
    lab_number: str
    name: str | None


class SampleSummary(BaseModel):
    id: int
    name: str
    case_type: str
    pipeline_key: str | None
    ingested_at: datetime | None
    workflow_status: str | None


class PatientDetailResponse(PatientSummary):
    created_at: datetime | None = None
    samples: list[SampleSummary]


class PatientListResponse(BaseModel):
    items: list[PatientSummary]
    total: int
    limit: int
    offset: int


@router.get("", response_model=PatientListResponse)
async def list_patients(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None),
):
    """Return a paginated list of patients with optional lab_number/name search."""
    where = ""
    base_params: tuple = ()
    if search:
        where = " WHERE lab_number ILIKE %s OR name ILIKE %s"
        base_params = (f"%{search}%", f"%{search}%")

    total_rows = await asyncio.to_thread(
        db.query,
        "SELECT COUNT(*) AS n FROM patients" + where,
        base_params,
    )
    total = total_rows[0]["n"]

    rows = await asyncio.to_thread(
        db.query,
        "SELECT id, lab_number, name FROM patients"
        + where
        + " ORDER BY lab_number LIMIT %s OFFSET %s",
        base_params + (limit, offset),
    )
    return PatientListResponse(
        items=[PatientSummary(**r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{patient_id}", response_model=PatientDetailResponse)
async def get_patient(patient_id: int):
    """Return patient detail including associated sample list."""
    rows = await asyncio.to_thread(
        db.query,
        "SELECT id, lab_number, name, created_at FROM patients WHERE id = %s",
        (patient_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Patient not found")

    sample_rows = await asyncio.to_thread(
        db.query,
        """
        SELECT s.id, s.name, s.case_type, s.pipeline_key, s.ingested_at,
               COALESCE(w.status, 'pending') AS workflow_status
        FROM samples s
        LEFT JOIN workflow w ON w.sample_id = s.id
        WHERE s.patient_id = %s
        ORDER BY s.ingested_at DESC NULLS LAST
        """,
        (patient_id,),
    )
    return PatientDetailResponse(
        **rows[0],
        samples=[SampleSummary(**s) for s in sample_rows],
    )
