"""Sample detail and sample variant list endpoints."""
from __future__ import annotations

import asyncio
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.lib import db
from app.middleware.auth import require_api_key


class PatientRef(BaseModel):
    """Slim patient reference used in nested contexts (no aggregate fields)."""
    id: int
    lab_number: str
    name: str | None

router = APIRouter(prefix="/api/samples", dependencies=[Depends(require_api_key)])


class _SampleNotFound(Exception):
    pass


class SampleDetailResponse(BaseModel):
    id: int
    name: str
    s3_key: str
    case_type: str
    pipeline_key: str | None
    tissue: str | None
    sequencing_date: date | None
    ingested_at: datetime | None
    patient: PatientRef
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
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    clinvar_sig: str | None = None
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
    patient = PatientRef(
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
    sort_by: str = Query("chrom", pattern="^(chrom|gene|gnomad_af|revel_score|spliceai_max|classification)$"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    gnomad_af_max: float | None = Query(None, ge=0, le=1),
    consequences: str | None = Query(None),
    clinvar_exclude: str | None = Query(None),
    gene: str | None = Query(None),
):
    """Return a paginated list of variants for a sample with classification summary."""
    sample_rows = await asyncio.to_thread(
        db.query,
        "SELECT 1 FROM samples WHERE id = %s",
        (sample_id,),
    )
    if not sample_rows:
        raise HTTPException(status_code=404, detail="Sample not found")

    # Build WHERE clause for filters
    filter_clauses = ["v.sample_id = %s"]
    filter_params: list = [sample_id]
    if gnomad_af_max is not None:
        filter_clauses.append("(v.gnomad_af IS NULL OR v.gnomad_af <= %s)")
        filter_params.append(gnomad_af_max)
    if consequences:
        csq_list = [c.strip() for c in consequences.split(",") if c.strip()]
        if csq_list:
            filter_clauses.append("v.consequence = ANY(%s)")
            filter_params.append(csq_list)
    if clinvar_exclude:
        excl_list = [c.strip() for c in clinvar_exclude.split(",") if c.strip()]
        if excl_list:
            filter_clauses.append(
                "(v.clinvar_sig IS NULL OR v.clinvar_sig != ALL(%s))"
            )
            filter_params.append(excl_list)
    if gene:
        filter_clauses.append("v.gene ILIKE %s")
        filter_params.append(gene)

    where_sql = " AND ".join(filter_clauses)

    total_rows = await asyncio.to_thread(
        db.query,
        f"SELECT COUNT(*) AS n FROM variants v WHERE {where_sql}",
        tuple(filter_params),
    )
    total = total_rows[0]["n"]

    # order_col and order_dir are safe to interpolate into SQL:
    # - sort_by is regex-validated by FastAPI (pattern=) before this function runs;
    #   any value not matching the pattern returns 422 before reaching here.
    # - SORTABLE values are source-code string literals, never user-derived.
    # - order_dir can only ever be the literal string "DESC" or "ASC".
    SORTABLE = {
        "chrom": "chrom_order, v.pos",
        "gene": "v.gene",
        "gnomad_af": "v.gnomad_af",
        "revel_score": "v.revel_score",
        "spliceai_max": "v.spliceai_max",
        "classification": "vc.classification",
    }
    order_col = SORTABLE.get(sort_by, "chrom_order, v.pos")
    order_dir = "DESC" if sort_dir == "desc" else "ASC"

    rows = await asyncio.to_thread(
        db.query,
        f"""
        SELECT v.id, v.chrom, v.pos, v.ref, v.alt, v.gene, v.consequence,
               v.hgvs_c, v.hgvs_p, v.clinvar_sig,
               v.gnomad_af, v.revel_score, v.spliceai_max,
               vc.classification, vc.score, vc.framework, vc.locked_at,
               CASE v.chrom
                   WHEN 'X'  THEN 23
                   WHEN 'Y'  THEN 24
                   WHEN 'MT' THEN 25
                   WHEN 'M'  THEN 25
                   -- TODO: bare chrom names assumed ('1'--'22', 'X', 'Y', 'MT').
                   -- DRAGEN chr-prefix ('chr1' etc.) will error on the ELSE cast.
                   -- Confirm chromosome format against a real lab VCF before deploying.
                   ELSE v.chrom::integer
               END AS chrom_order
        FROM variants v
        LEFT JOIN variant_classification vc
               ON vc.variant_id = v.id AND vc.deleted_at IS NULL
        WHERE {where_sql}
        ORDER BY {order_col} {order_dir}
        LIMIT %s OFFSET %s
        """,
        tuple(filter_params) + (limit, offset),
    )
    return VariantListResponse(
        items=[VariantSummary(**{k: v for k, v in r.items() if k != "chrom_order"}) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/{sample_id}", status_code=204)
async def delete_sample(sample_id: int):
    """Delete a sample and all associated variants and classifications."""
    def _do(conn):
        with conn.cursor() as c:
            c.execute("SELECT id FROM samples WHERE id = %s", (sample_id,))
            if not c.fetchone():
                raise _SampleNotFound()
            # CASCADE constraint removes variant_classification rows when variants
            # are deleted — no soft-delete step needed here (matches delete_patient pattern).
            c.execute("DELETE FROM variants WHERE sample_id = %s", (sample_id,))
            c.execute("DELETE FROM workflow WHERE sample_id = %s", (sample_id,))
            c.execute(
                "INSERT INTO audit_log "
                "(user_id, action, entity_type, entity_id, old_value, new_value) "
                "VALUES (%s, 'delete_sample', 'sample', %s, NULL, NULL)",
                ("system", sample_id),
            )
            c.execute("DELETE FROM samples WHERE id = %s", (sample_id,))

    try:
        await asyncio.to_thread(db.run_in_transaction, _do)
    except _SampleNotFound:
        raise HTTPException(status_code=404, detail="Sample not found")
