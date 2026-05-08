"""Pydantic data models mirroring the variant-viewer database schema.

Each class maps one-for-one to a database table.  The module also
exports shared ``Literal`` type aliases (``Framework``, ``Strength``,
``CaseType``, ``WorkflowStatus``, ``Classification``) that are re-used
across the business-logic layer.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel

Framework = Literal["acgs_snv", "svig"]
Strength = Literal["very_strong", "strong", "moderate", "supporting", "standalone"]
CaseType = Literal["germline", "somatic"]
WorkflowStatus = Literal["pending", "reviewing", "reported", "archived"]
Classification = Literal[
    "Pathogenic", "Likely_Pathogenic", "VUS",
    "Likely_Benign", "Benign", "Oncogenic", "Likely_Oncogenic"
]


class Patient(BaseModel):
    """Patient record mirroring the ``patients`` table.

    ``lab_number`` is the primary business key used for upsert; it must
    be unique across all patients.
    """

    id: int | None = None
    name: str | None = None
    lab_number: str
    created_at: datetime | None = None


class Sample(BaseModel):
    """Per-VCF sample record mirroring the ``samples`` table.

    ``s3_key`` uniquely identifies the source VCF object and is used for
    idempotency checks.  Multiple samples may exist for the same patient
    and specimen name (e.g. different gene panels from one specimen).
    """

    id: int | None = None
    patient_id: int
    name: str
    vcf_filename: str | None = None
    s3_key: str
    pipeline_key: str | None = None
    case_type: CaseType
    tissue: str | None = None
    sequencing_date: date | None = None
    ingested_at: datetime | None = None


class Variant(BaseModel):
    """Genomic variant record mirroring the ``variants`` table.

    One row is created per ALT allele per VCF data line.  Annotation
    fields are extracted from VEP CSQ or flat ``CSQ_*`` INFO fields by
    ``vcf_parser.parse_vcf()``.  ``info_json`` stores the full raw INFO
    dict for downstream use.
    """

    id: int | None = None
    sample_id: int
    chrom: str
    pos: int
    ref: str
    alt: str
    qual: float | None = None         # None when VCF field is "." (missing)
    filter: str | None = None
    gene: str | None = None
    consequence: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    gnomad_af: float | None = None
    clinvar_sig: str | None = None
    revel_score: float | None = None
    spliceai_max: float | None = None  # max of DS_AG / DS_AL / DS_DG / DS_DL
    info_json: dict[str, Any] = {}


class VariantClassification(BaseModel):
    """Classification record mirroring the ``variant_classification`` table.

    Created as a pending shell (``score`` and ``classification`` both
    ``None``) at ingest time to hold pre-computed criteria.  Locked by
    an analyst to produce the final classification.  Soft-deleted via
    ``deleted_at`` to allow reset without losing audit history.
    """

    id: int | None = None
    variant_id: int
    framework: Framework
    framework_version: str
    score: int | None = None          # None until analyst submits
    classification: Classification | None = None
    locked_at: datetime | None = None
    locked_by: str | None = None
    deleted_at: datetime | None = None  # soft-delete for reset


class ClassificationCriterion(BaseModel):
    """Individual criterion row mirroring the ``classification_criterion`` table.

    ``pre_computed=True`` rows are suggestions generated at ingest time;
    ``applied`` remains ``False`` until the analyst explicitly confirms
    the criterion.
    """

    id: int | None = None
    classification_id: int
    criterion_code: str
    applied: bool = False
    strength: Strength
    notes: str | None = None
    evidence_links: list[str] = []
    pre_computed: bool = False
    pre_computed_value: str | None = None


class WorkflowRecord(BaseModel):
    """Workflow status record mirroring the ``workflow`` table.

    One row per sample, tracking progress from ``pending`` through
    ``reviewing`` and ``reported`` to ``archived``.
    """

    id: int | None = None
    sample_id: int
    status: WorkflowStatus = "pending"
    updated_at: datetime | None = None
    updated_by: str | None = None


class AuditEntry(BaseModel):
    """Append-only audit log entry mirroring the ``audit_log`` table.

    ``old_value`` and ``new_value`` capture the JSON representation of
    the entity before and after the change.  The ``audit_log`` table is
    protected by a PostgreSQL trigger that prevents UPDATE and DELETE.
    """

    id: int | None = None
    user_id: str | None = None
    action: str
    entity_type: Literal["patient", "sample", "variant", "classification", "workflow"]
    entity_id: int
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    occurred_at: datetime | None = None
