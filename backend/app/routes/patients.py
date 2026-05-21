"""Patient list and detail endpoints."""
from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.lib import db
from app.middleware.auth import require_api_key

router = APIRouter(prefix="/api/patients", dependencies=[Depends(require_api_key)])


class _PatientNotFound(Exception):
    pass


class PatientSummary(BaseModel):
    id: int
    lab_number: str
    name: str | None
    # dob removed — dropped by migration 004 (UK GDPR data-minimisation)
    sample_count: int = 0
    latest_sample_id: int | None = None
    latest_sample_name: str | None = None
    latest_workflow_status: str | None = None
    latest_ingested_at: datetime | None = None
    pipeline_key: str | None = None


class SampleSummary(BaseModel):
    id: int
    name: str
    vcf_filename: str | None = None
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
        # Aggregate subqueries are safe here: each is bounded by patient_id index.
        # Five correlated subqueries for the latest-sample metadata are acceptable
        # at current scale; replace with LATERAL join if patient count > ~10k.
        """SELECT p.id, p.lab_number, p.name,
               COUNT(s.id) AS sample_count,
               (SELECT s2.id FROM samples s2 WHERE s2.patient_id = p.id
                ORDER BY s2.ingested_at DESC NULLS LAST LIMIT 1) AS latest_sample_id,
               (SELECT s2.name FROM samples s2 WHERE s2.patient_id = p.id
                ORDER BY s2.ingested_at DESC NULLS LAST LIMIT 1) AS latest_sample_name,
               (SELECT COALESCE(w2.status, 'pending') FROM samples s2
                LEFT JOIN workflow w2 ON w2.sample_id = s2.id
                WHERE s2.patient_id = p.id
                ORDER BY s2.ingested_at DESC NULLS LAST LIMIT 1) AS latest_workflow_status,
               (SELECT s2.ingested_at FROM samples s2 WHERE s2.patient_id = p.id
                ORDER BY s2.ingested_at DESC NULLS LAST LIMIT 1) AS latest_ingested_at,
               (SELECT s2.pipeline_key FROM samples s2 WHERE s2.patient_id = p.id
                ORDER BY s2.ingested_at DESC NULLS LAST LIMIT 1) AS pipeline_key
        FROM patients p
        LEFT JOIN samples s ON s.patient_id = p.id"""
        + (" WHERE p.lab_number ILIKE %s OR p.name ILIKE %s" if search else "")
        + " GROUP BY p.id ORDER BY p.lab_number LIMIT %s OFFSET %s",
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
        SELECT s.id, s.name, s.vcf_filename, s.case_type,
               s.pipeline_key, s.ingested_at,
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


@router.delete("/{patient_id}", status_code=204)
async def delete_patient(patient_id: int):
    """Delete a patient and all associated samples, variants, and classifications."""
    def _do(conn):
        with conn.cursor() as c:
            # Verify patient exists before deleting
            c.execute("SELECT id FROM patients WHERE id = %s", (patient_id,))
            if not c.fetchone():
                raise _PatientNotFound()
            # CASCADE constraint removes variant_classification rows when variants
            # are deleted — no soft-delete step needed here.
            c.execute(
                "DELETE FROM variants WHERE sample_id IN "
                "(SELECT id FROM samples WHERE patient_id = %s)",
                (patient_id,),
            )
            c.execute(
                "DELETE FROM workflow WHERE sample_id IN "
                "(SELECT id FROM samples WHERE patient_id = %s)",
                (patient_id,),
            )
            c.execute("DELETE FROM samples WHERE patient_id = %s", (patient_id,))
            # Audit before final delete so patient_id is still resolvable
            c.execute(
                "INSERT INTO audit_log "
                "(user_id, action, entity_type, entity_id, old_value, new_value) "
                "VALUES (%s, 'delete_patient', 'patient', %s, NULL, NULL)",
                ("system", patient_id),
            )
            c.execute("DELETE FROM patients WHERE id = %s", (patient_id,))

    try:
        await asyncio.to_thread(db.run_in_transaction, _do)
    except _PatientNotFound:
        raise HTTPException(status_code=404, detail="Patient not found")
