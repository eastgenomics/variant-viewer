"""Variant detail endpoint."""
from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.lib import db
from app.middleware.auth import require_api_key

router = APIRouter(prefix="/api/variants", dependencies=[Depends(require_api_key)])


class CriterionDetail(BaseModel):
    id: int
    criterion_code: str
    applied: bool
    strength: str
    notes: str | None
    evidence_links: list[str]
    pre_computed: bool
    pre_computed_value: str | None


class ClassificationDetail(BaseModel):
    id: int
    framework: str
    framework_version: str
    score: int | None
    classification: str | None
    locked_at: datetime | None
    locked_by: str | None
    criteria: list[CriterionDetail]


class VariantDetailResponse(BaseModel):
    id: int
    chrom: str
    pos: int
    ref: str
    alt: str
    gene: str | None
    consequence: str | None
    hgvs_c: str | None
    hgvs_p: str | None
    gnomad_af: float | None
    revel_score: float | None
    spliceai_max: float | None
    clinvar_sig: str | None
    info_json: dict
    active_classification: ClassificationDetail | None


@router.get("/{variant_id}", response_model=VariantDetailResponse)
async def get_variant(variant_id: int):
    """Return variant detail with active classification and applied criteria."""
    variant_rows = await asyncio.to_thread(
        db.query,
        """
        SELECT v.id, v.chrom, v.pos, v.ref, v.alt, v.gene, v.consequence,
               v.hgvs_c, v.hgvs_p, v.gnomad_af, v.revel_score, v.spliceai_max,
               v.clinvar_sig, v.info_json, s.case_type
        FROM variants v
        JOIN samples s ON s.id = v.sample_id
        WHERE v.id = %s
        """,
        (variant_id,),
    )
    if not variant_rows:
        raise HTTPException(status_code=404, detail="Variant not found")

    variant = variant_rows[0]

    classification_rows = await asyncio.to_thread(
        db.query,
        """
        SELECT id, framework, framework_version, score, classification,
               locked_at, locked_by
        FROM variant_classification
        WHERE variant_id = %s AND deleted_at IS NULL
        """,
        (variant_id,),
    )

    active_classification = None
    if classification_rows:
        clf = classification_rows[0]
        criteria_rows = await asyncio.to_thread(
            db.query,
            """
            SELECT id, criterion_code, applied, strength, notes, evidence_links,
                   pre_computed, pre_computed_value
            FROM classification_criterion
            WHERE classification_id = %s ORDER BY id
            """,
            (clf["id"],),
        )
        active_classification = ClassificationDetail(
            **clf,
            criteria=[CriterionDetail(**c) for c in criteria_rows],
        )

    return VariantDetailResponse(
        id=variant["id"],
        chrom=variant["chrom"],
        pos=variant["pos"],
        ref=variant["ref"],
        alt=variant["alt"],
        gene=variant["gene"],
        consequence=variant["consequence"],
        hgvs_c=variant["hgvs_c"],
        hgvs_p=variant["hgvs_p"],
        gnomad_af=variant["gnomad_af"],
        revel_score=variant["revel_score"],
        spliceai_max=variant["spliceai_max"],
        clinvar_sig=variant["clinvar_sig"],
        info_json=variant["info_json"],
        active_classification=active_classification,
    )
